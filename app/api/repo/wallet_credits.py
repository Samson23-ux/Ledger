from app.api.repo.base import BaseRepository
from app.api.models.wallet_credits import WalletCredit
from app.api.schemas.wallet_credits import WalletCreditBase


class WalletCreditRepository(BaseRepository[WalletCreditBase, WalletCredit]):
    model = WalletCredit

    def _entity_to_model(self, entity):
        return WalletCredit(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "wallet_id" in filters:
            filter_conditions.append(self.model.wallet_id == filters["wallet_id"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        sortable_fields = {"created_at": self.model.created_at}
        return [sortable_fields.get(sort, self.model.created_at)]
