from enum import Enum
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta, timezone

from app.api.repo.redis import RedisRepository


class CircuitState(str, Enum):
    OPEN = "open"
    HALFOPEN = "half_open"
    CLOSED = "closed"


class CircuitBreaker:
    """Circuit breaker backed by Redis.

    `check` gates a request against paystack's server current state,
    returning a 503 to short-circuit on when the instance shouldn't be called.
    `record_success` / `record_failure` drive the closed -> open ->
    half-open state machine from the outcome of a call that was let through.
    """

    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 30
    HALF_OPEN_REQUESTS = 2

    def __init__(self, redis: RedisRepository):
        self._redis = redis

    @staticmethod
    def _breaker_key() -> str:
        return "paystack:circuit"

    @staticmethod
    def _unavailable(retry_at: str) -> JSONResponse:
        return JSONResponse(
            content="Service Unavailable",
            status_code=503,
            headers={"retry_after": retry_at},
        )

    def _retry_at(self):
        return (
            datetime.now(timezone.utc) + timedelta(seconds=self.RECOVERY_TIMEOUT)
        ).isoformat()

    async def initialize(self):
        breaker_key = self._breaker_key()
        circuit = await self._redis.get_hset(breaker_key)

        if not circuit:
            await self._redis.create_hset(
                breaker_key,
                {
                    "failures": 0,
                    "state": CircuitState.CLOSED,
                    "retry_at": "None",
                    "half_open_requests": 0,
                },
            )

    async def check(self) -> dict:
        """Returns the current circuit and, when the instance should be
        rejected, the 503 response to short-circuit the request with.
        """
        breaker_key = self._breaker_key()
        circuit = await self._redis.get_hset(breaker_key)

        circuit["failures"] = int(circuit["failures"])
        circuit["half_open_requests"] = int(circuit["half_open_requests"])

        if circuit["state"] == CircuitState.OPEN:
            retry_at = datetime.fromisoformat(circuit["retry_at"])

            if datetime.now(timezone.utc) >= retry_at:
                circuit["half_open_requests"] += 1
                circuit["state"] = CircuitState.HALFOPEN

                await self._redis.create_hset(
                    breaker_key,
                    {
                        "state": circuit["state"],
                        "half_open_requests": circuit["half_open_requests"],
                    },
                )
            else:
                return {
                    "is_healthy": False,
                    "retry_after": circuit["retry_at"],
                }
        elif circuit["state"] == CircuitState.HALFOPEN:
            if circuit["half_open_requests"] >= self.HALF_OPEN_REQUESTS:
                circuit["state"] = CircuitState.OPEN
                circuit["retry_at"] = self._retry_at()

                await self._redis.create_hset(
                    breaker_key,
                    {
                        "half_open_requests": 0,
                        "state": circuit["state"],
                        "retry_at": circuit["retry_at"],
                    },
                )
                return {
                    "is_healthy": False,
                    "retry_after": circuit["retry_at"],
                }
            else:
                circuit["half_open_requests"] += 1
                await self._redis.create_hset(
                    breaker_key, {"half_open_requests": circuit["half_open_requests"]}
                )

        return {"is_healthy": True}

    async def record_success(self):
        breaker_key = self._breaker_key()
        circuit = await self._redis.get_hset(breaker_key)

        if circuit["state"] == CircuitState.CLOSED:
            circuit["failures"] = 0
        elif (
            circuit["state"] == CircuitState.HALFOPEN
            and circuit["half_open_requests"] >= 2
        ):
            circuit["failures"] = 0
            circuit["retry_at"] = "None"
            circuit["half_open_requests"] = 0
            circuit["state"] = CircuitState.CLOSED

        await self._redis.create_hset(breaker_key, circuit)

    async def record_failure(self) -> dict | None:
        """Registers a failed call against the breaker. Returns the 503
        response when this failure trips the circuit open, else None.
        """
        breaker_key = self._breaker_key()
        circuit = await self._redis.get_hset(breaker_key)

        circuit["failures"] += 1
        breaker_key = self._breaker_key()
        circuit["retry_at"] = self._retry_at()

        if circuit["state"] == CircuitState.HALFOPEN:
            await self._redis.create_hset(
                breaker_key,
                {
                    "half_open_requests": 0,
                    "state": CircuitState.OPEN,
                    "retry_at": circuit["retry_at"],
                },
            )
            return {
                "is_healthy": False,
                "retry_after": circuit["retry_at"],
            }
        elif (
            circuit["state"] == CircuitState.CLOSED
            and circuit["failures"] >= self.FAILURE_THRESHOLD
        ):
            await self._redis.create_hset(
                breaker_key,
                {
                    "failures": circuit["failures"],
                    "half_open_requests": 0,
                    "state": CircuitState.OPEN,
                    "retry_at": circuit["retry_at"],
                },
            )
            return {
                "is_healthy": False,
                "retry_after": circuit["retry_at"],
            }

        await self._redis.create_hset(breaker_key, {"failures": circuit["failures"]})
        return None
