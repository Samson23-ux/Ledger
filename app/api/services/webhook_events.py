import sentry_sdk
from uuid import uuid7
import sentry_sdk.logger as sentry_logger


from app.core.security import Security
from app.core.exceptions import ServerError
from app.api.schemas.outbox import OutBoxCreate
from app.api.repo.outbox import OutBoxRepository
from app.api.services.outbox import OutBoxService
from app.api.repo.uow import UnitOfWorkRepository
from app.api.schemas.webhook_events import WebhookEventCreate
from app.api.repo.webhook_events import WebhookEventRepository
from app.worker.tasks.webhook_events import process_webhook_events


class WebhookEventService:
    def __init__(self, webhook_repo: WebhookEventRepository):
        self._webhook_repo = webhook_repo

    async def _setup_uow(self, uow: UnitOfWorkRepository):
        self._uow = uow

    async def _uow_webhook(self, uow: UnitOfWorkRepository):
        await self._setup_uow(uow)

        out_box_repo = self._uow.repo(OutBoxRepository)
        self._out_box_service = OutBoxService(out_box_repo=out_box_repo)

    async def _get_outbox_payload(self, payload: dict) -> OutBoxCreate:
        return OutBoxCreate(
            id=uuid7(),
            event_type="webhook",
            payload=payload,
        )

    async def _get_webhook_payload(
        self, event: str, payload: dict, user_email: str = None
    ) -> tuple[WebhookEventCreate, dict]:
        webhook_create, task_payload = None, None

        payload_data = payload["data"]

        if event == "charge.success":
            webhook_create = WebhookEventCreate(
                id=uuid7(),
                paystack_data_id=payload_data["id"],
                paystack_reference=payload_data["reference"],
                event_type=event,
                payload=payload,
                signature_verified=True,
            )

            task_payload: dict = {
                "event": event,
                "reference": payload_data["reference"],
                "card_type": payload_data["authorization"]["card_type"],
                "country_code": payload_data["authorization"]["country_code"],
                "code_reusable": payload_data["authorization"]["reusable"],
                "expiry_year": payload_data["authorization"]["exp_year"],
                "expiry_month": payload_data["authorization"]["exp_month"],
                "gateway_response": payload_data["gateway_response"],
                "authorization_code": payload_data["authorization"][
                    "authorization_code"
                ],
                "message_id": str(uuid7()),
            }

            if payload_data["channel"] == "bank_transfer":
                task_payload["sender_bank_account_number"] = payload_data[
                    "authorization"
                ]["sender_bank_account_number"]
        elif event == "bank.transfer.rejected":
            webhook_create = WebhookEventCreate(
                id=uuid7(),
                paystack_data_id=payload_data["customer"]["id"],
                event_type=event,
                payload=payload,
                signature_verified=True,
            )

            task_payload: dict = {
                "event": event,
                "transaction_id": payload_data["bank_transfer"]["transaction_id"],
                "message_id": str(uuid7()),
            }
        elif event.startswith("refund"):
            webhook_create = WebhookEventCreate(
                id=uuid7(),
                paystack_reference=payload_data["transaction_reference"],
                event_type=event,
                payload=payload,
                signature_verified=True,
            )

            task_payload: dict = {
                "event": event,
                "reference": payload_data["transaction_reference"],
                "message_id": str(uuid7()),
            }

            if event == "refund.needs-attention":
                webhook_create.paystack_data_id = payload_data["id"]

        return webhook_create, task_payload

    async def process_webhook_event(
        self,
        security: Security,
        signature: str,
        payload: dict,
        uow: UnitOfWorkRepository,
    ):
        try:
            await self._uow_webhook(uow)

            is_signature_valid = await security.verify_webhook_signature(
                signature, payload
            )

            if is_signature_valid:
                event = payload["event"]
                webhook_create, task_payload = await self._get_webhook_payload(
                    event, payload
                )

                outbox_create = await self._get_outbox_payload(task_payload)

                webhook_event = await self._webhook_repo.create_webhook_event(
                    webhook_create
                )

                if (
                    webhook_event.id == webhook_create.id
                    and not webhook_event.processed
                ):
                    """The created  id for the received event matches
                    the inserted row and should be passed on to the background task.

                    A duplicate is detected when the created id does not match the
                    returned row's id"""

                    await self._out_box_service._create_out_box(outbox_create)
                    process_webhook_events.apply_async(
                        priority=5, kwargs={"payload": task_payload}
                    )

            sentry_logger.info(
                "Webhook event processed successfully",
                extra={"event": payload["event"]},
            )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing webhook event", extra={"exc": str(exc)}
            )

            raise ServerError() from exc
