from app.api.models.refunds import Refund
from app.api.repo.base import BaseRepository
from app.api.schemas.refunds import RefundBase


class RefundRepository(BaseRepository[RefundBase, Refund]):
    model = Refund

    def _entity_to_model(self, entity):
        return Refund(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "user_id" in filters:
            filter_conditions.append(self.model.user_id == filters["user_id"])
        if "payment_transaction_id" in filters:
            filter_conditions.append(
                self.model.payment_transaction_id == filters["payment_transaction_id"]
            )
        if "status" in filters:
            filter_conditions.append(self.model.status == filters["status"])

    def _get_sort_fields(self, sort):
        sortable_fields = {
            "created_at": self.model.created_at,
            "updated_at": self.model.updated_at,
        }
        return [sortable_fields.get(sort, self.model.created_at)]
