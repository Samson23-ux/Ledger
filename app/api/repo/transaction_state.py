from app.api.repo.base import BaseRepository
from app.api.schemas.transaction_state import TransactionStateBase
from app.api.models.transaction_state_events import TransactionStateEvent


class TransactionStateRepository(BaseRepository[TransactionStateBase, TransactionStateEvent]):
    model = TransactionStateEvent

    def _entity_to_model(self, entity):
        return TransactionStateEvent(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "entity_type" in filters:
            filter_conditions.append(self.model.entity_type == filters["entity_type"])
        if "entity_id" in filters:
            filter_conditions.append(self.model.entity_id == filters["entity_id"])
        if "from_status" in filters:
            filter_conditions.append(self.model.from_status == filters["from_status"])
        if "to_status" in filters:
            filter_conditions.append(self.model.to_status == filters["to_status"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)
