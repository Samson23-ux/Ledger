from uuid import UUID


from app.api.models.wallet_credits import WalletCredit
from app.api.repo.wallet_credits import WalletCreditRepository
from app.api.schemas.wallet_credits import WalletCreditCreate


class WalletCreditService:
    def __init__(self, credit_repo: WalletCreditRepository):
        self._credit_repo = credit_repo

    async def _get_wallet_credit(
        self, wallet_id: UUID, credit_id: UUID
    ) -> WalletCredit:
        return await self._credit_repo.get_record(id=credit_id, wallet_id=wallet_id)

    def _create_wallet_credit_sync(
        self, wallet_credit_create: WalletCreditCreate
    ) -> WalletCredit:
        return self._credit_repo.sync_add(entity=wallet_credit_create)

    async def _get_wallet_credits(
        self, cursor: str | None, sort: str | None, order: str, limit: int, **filters
    ) -> dict:
        return await self._credit_repo.get_records(
            sort, order, cursor, limit, **filters
        )
