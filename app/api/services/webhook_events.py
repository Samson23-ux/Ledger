from uuid import uuid7


from app.core.security import Security
from app.api.schemas.webhook_events import WebhookEventCreate
from app.api.repo.webhook_events import WebhookEventRepository


class WebhookEventService:
    def __init__(self, webhook_repo: WebhookEventRepository):
        self._webhook_repo = webhook_repo

    async def process_webhook_event(
        self, security: Security, signature: str, payload: str
    ):
        is_signature_valid = await security.verify_webhook_signature(signature, payload)

        if is_signature_valid:
            webhook_create = WebhookEventCreate(
                id=uuid7(),
                paystack_data_id=payload["data"]["id"],
                paystack_reference=["data"]["reference"],
                event_type=payload["event"],
                payload=payload,
                signature_verified=True
            )

            webhook_event = await self._webhook_repo.create_webhook_event(
                webhook_create
            )

            if webhook_event.id == webhook_create.id and not webhook_event.processed:
                """The created  id for the received event matches
                the inserted row and should be passed on to the background task.

                A duplicate is detected when the created id does not match the
                returned row's id"""

                # pass to celery task to return 200 response to paystack immediately
