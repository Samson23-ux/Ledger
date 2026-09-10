from app.api.models.wallets import Wallet
from app.api.repo.base import BaseRepository
from app.api.schemas.wallets import WalletBase


class WalletRepository(BaseRepository[WalletBase, Wallet]):
    model = Wallet

    def _entity_to_model(self, entity):
        return Wallet(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "user_id" in filters:
            filter_conditions.append(self.model.user_id == filters["user_id"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)
