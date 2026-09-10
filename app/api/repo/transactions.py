from sqlalchemy.dialects.postgresql import insert


from app.api.repo.base import BaseRepository
from app.api.models.transactions import PaymentTransaction
from app.api.schemas.transactions import TransactionBase, TransactionCreate


class TransactionRepository(BaseRepository[TransactionBase, PaymentTransaction]):
    model = PaymentTransaction

    def _entity_to_model(self, entity):
        return PaymentTransaction(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "user_id" in filters:
            filter_conditions.append(self.model.user_id == filters["user_id"])
        if "wallet_id" in filters:
            filter_conditions.append(self.model.wallet_id == filters["wallet_id"])
        if "idempotency_key" in filters:
            filter_conditions.append(
                self.model.idempotency_key == filters["idempotency_key"]
            )
        if "paystack_reference" in filters:
            filter_conditions.append(
                self.model.paystack_reference == filters["paystack_reference"]
            )
        if "status" in filters:
            filter_conditions.append(self.model.status == filters["status"])

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)

    async def create_transaction(self, transaction: TransactionCreate):
        insert_stmt = insert(self.model).values(**transaction.model_dump())
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["idempotency_key"],
            set_={"idempotency_key": insert_stmt.excluded.idempotency_key},
        ).returning(self.model)

        res = await self._async_session.execute(stmt)
        return res.scalar()
