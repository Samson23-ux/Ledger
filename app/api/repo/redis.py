import time
from redis.asyncio import Redis
from redis import Redis as SyncRedis


LOCK_TTL = 8
LOCK_TIMEOUT = 10
LOCK_INTERVAL = 1


class RedisRepository:
    def __init__(self, async_redis: Redis = None, sync_redis: SyncRedis = None):
        self._sync_redis = sync_redis
        self._async_redis = async_redis

    async def create_hset(self, key: str, value: dict):
        await self._async_redis.hset(key, mapping=value)

    async def get_hset(self, key: str) -> dict:
        return await self._async_redis.hgetall(key)

    def create_hset_sync(self, key: str, value: dict):
        self._sync_redis.hset(key, mapping=value)

    def get_hset_sync(self, key: str) -> dict:
        return self._sync_redis.hgetall(key)

    async def set_key(self, key: str, value: str, ttl: int):
        await self._async_redis.set(key, value, ex=ttl)

    async def get_key(self, key: str) -> str | None:
        return await self._async_redis.get(key)

    async def delete_key(self, key: str):
        await self._async_redis.delete(key)

    async def acquire_lock(self, key: str, token: str, ttl: int = LOCK_TTL):
        return await self._async_redis.set(key, token, ex=ttl, nx=True)

    async def release_lock(self, key: str, token: str):
        set_token = await self._async_redis.get(key)

        if token == set_token:
            await self._async_redis.delete(key)

    async def access_resource(self, key: str, token: str):
        set_token = await self.acquire_lock(key, token)

        wait_time = 0
        while not set_token and wait_time < LOCK_TIMEOUT:
            time.sleep(LOCK_INTERVAL)
            wait_time += LOCK_INTERVAL

            set_token = self.acquire_lock(key, token)
        return set_token

    def get_idempotency_key(self, key: str) -> str | None:
        return self._sync_redis.get(key)

    def mark_idempotency_key(self, key: str, value: str, ttl: int):
        self._sync_redis.set(key, value, ex=ttl)

    def acquire_lock_sync(self, key: str, token: str, ttl: int = LOCK_TTL):
        return self._sync_redis.set(key, token, ex=ttl, nx=True)

    def release_lock_sync(self, key: str, token: str):
        set_token = self._sync_redis.get(key)

        if token == set_token:
            self._sync_redis.delete(key)

    def access_resource_sync(self, key: str, token: str):
        set_token = self.acquire_lock_sync(key, token)

        wait_time = 0.0
        while not set_token and wait_time < LOCK_TIMEOUT:
            time.sleep(LOCK_INTERVAL)
            wait_time += LOCK_INTERVAL

            set_token = self.acquire_lock_sync(key, token)
        return set_token
