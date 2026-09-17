from uuid import UUID
from sqlalchemy import select, or_, update
from datetime import datetime, timezone, timedelta


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
        if "reconcile" in filters:
            filter_conditions.append(
                or_(self.model.status == "pending", self.model.status == "initiated")
            )

        return filter_conditions

    def _get_sort_fields(self, sort):
        sortable_fields = {
            "created_at": self.model.created_at,
            "updated_at": self.model.updated_at,
        }
        return [sortable_fields.get(sort, self.model.created_at)]

    def get_pending_refunds(self, **filters):
        filter_conditions = self._get_filters(**filters)
        stmt = select(self.model).where(
            *filter_conditions,
            self.model.created_at <= datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        res = self.sync_session.execute(stmt)
        return res.scalars().all()

    async def get_refund(self, transaction_id: UUID):
        stmt = (
            select(self.model)
            .where(self.model.payment_transaction_id == transaction_id)
            .order_by(self.model.created_at)
        )

        res = await self.async_session.execute(stmt)
        refunds = res.scalars().all()

        return refunds[-1] if refunds else None

    def _update_refund_records(self, records: list[dict]):
        self.sync_session.execute(update(self.model), records)
