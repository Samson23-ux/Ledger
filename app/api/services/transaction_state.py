import sentry_sdk
from uuid import UUID
import sentry_sdk.logger as sentry_logger


from app.api.models.user import User
from app.api.repo.transaction_state import TransactionStateRepository
from app.core.exceptions import ServerError, TransactionStateNotFoundError
from app.api.schemas.transaction_state import (
    TransactionStateCreate,
    TransactionStateResponse,
)


class TransactionStateService:
    def __init__(self, state_repo: TransactionStateRepository):
        self._state_repo = state_repo

    async def _create_transaction_state(self, state_create: TransactionStateCreate):
        self._state_repo.add(entity=state_create)

    async def get_transaction_state(
        self, id: UUID, curr_user: User
    ) -> list[TransactionStateResponse]:
        try:
            user_id = curr_user.id
            transaction_state_db = await self._state_repo.get_transaction_state(id)

            if not transaction_state_db:
                sentry_logger.error(
                    "Transaction state not found",
                    extra={"user_id": user_id, "transaction_id": id},
                )

            transaction_state = []
            for state in transaction_state_db:
                transaction_state.append(TransactionStateResponse.model_validate(state))

            sentry_logger.info(
                "Transaction state retrieved successfully",
                extra={"user_id": user_id, "transaction_id": id},
            )
            return transaction_state
        except Exception as exc:
            if isinstance(exc, TransactionStateNotFoundError):
                raise TransactionStateNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transaction state",
                extra={"user_id": user_id, "id": id},
            )
            raise ServerError() from exc
