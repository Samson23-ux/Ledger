from sqlalchemy.dialects.postgresql import insert


from app.api.repo.base import BaseRepository
from app.api.models.webhook_events import WebhookEvent
from app.api.schemas.webhook_events import WebhookEventBase, WebhookEventCreate


class WebhookEventRepository(BaseRepository[WebhookEventBase, WebhookEvent]):
    model = WebhookEvent

    def _entity_to_model(self, entity):
        return WebhookEvent(**entity.model_dump())

    def _get_filters(self, **filters):
        filter_conditions = []

        if "id" in filters:
            filter_conditions.append(self.model.id == filters["id"])
        if "paystack_event_id" in filters:
            filter_conditions.append(
                self.model.paystack_event_id == filters["paystack_event_id"]
            )

        return filter_conditions

    def _get_sort_fields(self, sort):
        return super()._get_sort_fields(sort)

    async def create_webhook_event(self, event: WebhookEventCreate):
        insert_stmt = insert(self.model).values(**event.model_dump())
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["paystack_data_id", "paystack_reference", "event_type"],
            set_={"paystack_reference": insert_stmt.excluded.paystack_reference},
        ).returning(self.model)

        res = await self._async_session.execute(stmt)
        return res.scalar()
