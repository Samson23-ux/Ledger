from uuid import UUID
from sqlalchemy import select, insert


from app.api.repo.base import BaseRepository
from app.api.schemas.refund_state import RefundStateBase
from app.api.models.refund_state_events import RefundStateEvent


class RefundStateRepository(
    BaseRepository[RefundStateBase, RefundStateEvent]
):
    model = RefundStateEvent

    def _entity_to_model(self, entity):
        return RefundStateEvent(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "refund_id" in filters:
            filter_conditions.append(
                self.model.refund_id == filters["refund_id"]
            )
        if "from_status" in filters:
            filter_conditions.append(self.model.from_status == filters["from_status"])
        if "to_status" in filters:
            filter_conditions.append(self.model.to_status == filters["to_status"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)

    async def get_refund_state(self, id: UUID):
        stmt = select(self.model).where(self.model.refund_id == id)
        res = await self._async_session.execute(stmt)
        return res.scalars().all()

    def create_state_records(self, records: list[dict]):
        self.sync_session.execute(insert(self.model), records)
