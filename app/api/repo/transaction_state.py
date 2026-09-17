from uuid import UUID
from sqlalchemy import select, insert


from app.api.repo.base import BaseRepository
from app.api.schemas.transaction_state import TransactionStateBase
from app.api.models.transaction_state_events import TransactionStateEvent


class TransactionStateRepository(
    BaseRepository[TransactionStateBase, TransactionStateEvent]
):
    model = TransactionStateEvent

    def _entity_to_model(self, entity):
        return TransactionStateEvent(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "transaction_id" in filters:
            filter_conditions.append(
                self.model.transaction_id == filters["transaction_id"]
            )
        if "from_status" in filters:
            filter_conditions.append(self.model.from_status == filters["from_status"])
        if "to_status" in filters:
            filter_conditions.append(self.model.to_status == filters["to_status"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)

    async def get_transaction_state(self, id: UUID):
        stmt = select(self.model).where(self.model.transaction_id == id)
        res = await self._async_session.execute(stmt)
        return res.scalars().all()

    def create_state_records(self, records: list[dict]):
        self.sync_session.execute(insert(self.model), records)
