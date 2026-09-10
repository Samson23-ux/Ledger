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
