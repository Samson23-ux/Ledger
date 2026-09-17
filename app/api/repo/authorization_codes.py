from sqlalchemy.dialects.postgresql import insert


from app.api.repo.base import BaseRepository
from app.api.models.authorization_codes import AuthorizationCode
from app.api.schemas.authorization_codes import AuthCodeBase, AuthCodesCreate


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

    def _create_auth_code(self, code_create: AuthCodesCreate):
        insert_stmt = (
            insert(self.model)
            .values(**code_create.model_dump())
            .on_conflict_do_nothing(index_elements=["wallet_id"])
        )
        self.sync_session.execute(insert_stmt)
