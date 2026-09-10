from app.api.repo.base import BaseRepository
from app.api.schemas.authorization_codes import AuthCodeBase
from app.api.models.authorization_codes import AuthorizationCode


class AuthCodeRepository(BaseRepository[AuthCodeBase, AuthorizationCode]):
    model = AuthorizationCode

    def _entity_to_model(self, entity):
        return AuthorizationCode(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "wallet_id" in filters:
            filter_conditions.append(self.model.wallet_id == filters["wallet_id"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)
