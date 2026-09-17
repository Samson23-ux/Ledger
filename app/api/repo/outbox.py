from sqlalchemy import select, update


from app.api.models.outbox import OutBox
from app.api.repo.base import BaseRepository
from app.api.schemas.outbox import OutBoxBase


class OutBoxRepository(BaseRepository[OutBoxBase, OutBox]):
    model = OutBox

    def _entity_to_model(self, entity):
        return OutBox(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "status" in filters:
            filter_conditions.append(self.model.status == filters["status"])
        if "event_type" in filters:
            filter_conditions.append(self.model.event_type == filters["event_type"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)

    def _get_outbox_records(self, **filters):
        filter_conditions = self._get_filters(**filters)

        stmt = select(self.model).where(*filter_conditions).with_for_update()
        res = self.sync_session.execute(stmt)

        return res.scalars().all()

    def _update_outbox_records(self, records: list[dict]):
        self.sync_session.execute(update(self.model), records)
