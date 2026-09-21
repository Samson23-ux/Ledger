import sentry_sdk
from uuid import UUID
import sentry_sdk.logger as sentry_logger


from app.api.models.user import User
from app.api.repo.refund_state import RefundStateRepository
from app.core.exceptions import ServerError, RefundStateNotFoundError
from app.api.schemas.refund_state import RefundStateCreate, RefundStateResponse


class RefundStateService:
    def __init__(self, state_repo: RefundStateRepository):
        self._state_repo = state_repo

    async def _create_refund_state(self, state_create: RefundStateCreate):
        self._state_repo.add(entity=state_create)

    def _get_refund_state_sync(self, **filters):
        return self._state_repo.get_sync_record(**filters)

    def _create_state_records(self, records: list[dict]):
        self._state_repo.create_state_records(records)

    def _create_refund_state_sync(self, state_create: RefundStateCreate):
        return self._state_repo.sync_add(entity=state_create)

    async def get_refund_state(
        self, id: UUID, curr_user: User
    ) -> list[RefundStateResponse]:
        try:
            user_id = curr_user.id
            refund_state_db = await self._state_repo.get_refund_state(id)

            if not refund_state_db:
                sentry_logger.error(
                    "Refund state not found",
                    extra={"user_id": user_id, "refund_id": id},
                )
                raise RefundStateNotFoundError(id)

            refund_state = []
            for state in refund_state_db:
                refund_state.append(RefundStateResponse.model_validate(state))

            sentry_logger.info(
                "Refund state retrieved successfully",
                extra={"user_id": user_id, "refund_id": id},
            )
            return refund_state
        except Exception as exc:
            print(f"EXCEPTION ========>>>>> {exc}")
            if isinstance(exc, RefundStateNotFoundError):
                raise RefundStateNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transaction state",
                extra={"user_id": user_id, "id": id},
            )
            raise ServerError() from exc
