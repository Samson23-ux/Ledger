import sentry_sdk
from uuid import UUID
import sentry_sdk.logger as sentry_logger


from app.api.models.user import User
from app.api.services.thread_pool import ThreadPool
from app.api.models.transactions import PaymentTransaction
from app.api.schemas.transactions import TransactionCreate
from app.api.models.transactions import PaymentTransaction
from app.api.repo.transactions import TransactionRepository
from app.api.schemas.transactions import TransactionResponse
from app.core.exceptions import (
    ServerError,
    TransactionNotFoundError,
    TransactionsNotFoundError,
)


class TransactionService:
    def __init__(
        self,
        pool: ThreadPool,
        transaction_repo: TransactionRepository,
    ):
        self._pool = pool
        self._transaction_repo = transaction_repo

    async def _create_transaction(
        self, transaction_create: TransactionCreate
    ) -> PaymentTransaction:
        return await self._transaction_repo.create_transaction(transaction_create)

    async def _get_transaction(self, **filters) -> PaymentTransaction | None:
        return await self._transaction_repo.get_record(**filters)

    async def _update_transaction(self, transaction: PaymentTransaction):
        self._transaction_repo.add(model=transaction)

    def _get_pending_transactions(self, **filters):
        return self._transaction_repo.get_pending_transactions(**filters)

    def _get_transaction_sync(self, **filters) -> PaymentTransaction:
        return self._transaction_repo.get_sync_record(**filters)

    def _update_transaction_records(self, records: list[dict]):
        self._transaction_repo._update_transaction_records(records)

    def _update_transaction_sync(self, transaction: PaymentTransaction):
        self._transaction_repo.sync_add(model=transaction)

    async def get_transactions(
        self,
        curr_user: User,
        cursor: str | None,
        sort: str | None,
        order: str,
        limit: int,
    ) -> list[TransactionResponse]:
        try:
            user_id = curr_user.id

            res = await self._transaction_repo.get_records(
                sort, order, cursor, limit, user_id=user_id
            )

            transactions_db = res.get("data")
            if not transactions_db:
                sentry_logger.error(
                    "Transactions not found", extra={"user_id": user_id}
                )
                raise TransactionsNotFoundError()

            transactions = []
            for transaction in transactions_db:
                transactions.append(TransactionResponse.model_validate(transaction))

            sentry_logger.info(
                "Transactions retrieved successfully", extra={"user_id": user_id}
            )
            return transactions, res.get("cursor")
        except Exception as exc:
            if isinstance(exc, TransactionsNotFoundError):
                raise TransactionsNotFoundError()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transactions",
                extra={"user_id": user_id},
            )
            raise ServerError() from exc

    async def get_transaction(self, id: UUID, curr_user: User) -> TransactionResponse:
        try:
            user_id = curr_user.id
            transaction = await self._transaction_repo.get_record(
                id=id, user_id=user_id
            )

            if not transaction:
                sentry_logger.error(
                    "Transaction not found",
                    extra={"user_id": user_id, "transaction_id": id},
                )
                raise TransactionNotFoundError(id=id)

            sentry_logger.info(
                "Transaction retrieved successfully",
                extra={"user_id": user_id, "transaction_id": id},
            )
            return TransactionResponse.model_validate(transaction)
        except Exception as exc:
            if isinstance(exc, TransactionNotFoundError):
                raise TransactionNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transaction",
                extra={"user_id": user_id, "transaction_id": id},
            )
            raise ServerError() from exc
