from uuid import UUID


from app.api.models.user import User
from app.api.models.wallet_credits import WalletCredit
from app.api.repo.wallet_credits import WalletCreditRepository


class WalletCreditService:
    def __init__(self, credit_repo: WalletCreditRepository):
        self._credit_repo = credit_repo

    async def _get_wallet_credit(
        self, wallet_id: UUID, credit_id: UUID
    ) -> WalletCredit:
        return await self._credit_repo.get_record(id=credit_id, wallet_id=wallet_id)

    async def _get_wallet_credits(
        self, cursor: str | None, sort: str | None, order: str, limit: int, **filters
    ) -> dict:
        return await self._credit_repo.get_records(
            sort, order, cursor, limit, **filters
        )
