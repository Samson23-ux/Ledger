from app.api.schemas.transaction_state import TransactionStateCreate
from app.api.repo.transaction_state import TransactionStateRepository


class TransactionStateService:
    def __init__(self, state_repo: TransactionStateRepository):
        self._state_repo = state_repo

    async def _create_transaction_state(self, state_create: TransactionStateCreate):
        self._state_repo.add(entity=state_create)
