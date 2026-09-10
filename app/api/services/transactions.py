from app.api.schemas.transactions import TransactionCreate
from app.api.models.transactions import PaymentTransaction
from app.api.repo.transactions import TransactionRepository


class TransactionService:
    def __init__(self, transaction_repo: TransactionRepository):
        self._transaction_repo = transaction_repo

    async def _create_transaction(
        self, transaction_create: TransactionCreate
    ) -> PaymentTransaction:
        return await self._transaction_repo.create_transaction(transaction_create)

    async def _get_transaction(self, **filters) -> PaymentTransaction | None:
        return await self._transaction_repo.get_record(**filters)
