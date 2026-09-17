import sentry_sdk
from uuid import uuid4
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import sentry_sdk.logger as sentry_logger


from app.worker import get_redis_repo
from app.api.schemas.outbox import OutBoxInDB
from app.api.repo.outbox import OutBoxRepository
from app.api.services.outbox import OutBoxService
from app.worker.services.webhooks import TaskWebhook
from app.worker.services.transactions import TaskRefund, TaskTransaction


class OutBoxTask:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id

        self._session = session
        self._redis_repo = get_redis_repo()

        self._task_refund = TaskRefund(self.task_id, self._session)
        self._task_webhook = TaskWebhook(self.task_id, self._session)
        self._task_transaction = TaskTransaction(self.task_id, self._session)

        self._outbox_service = OutBoxService(
            out_box_repo=OutBoxRepository(sync_session=self._session)
        )

    def outbox_charge_authorization(self, payload: dict):
        email = payload.get("email")
        amount = payload.get("amount")
        currency = payload.get("currency")
        transaction_id = payload.get("transaction_id")
        authorization_code = payload.get("authorization_code")

        resource_token = str(uuid4())
        resource = self._redis_repo.access_resource_sync(
            f"charge:{transaction_id}", resource_token
        )

        if resource:
            self._task_transaction.charge_authorization(
                email, amount, currency, authorization_code, transaction_id
            )

            self._redis_repo.release_lock_sync(
                f"charge:{transaction_id}", resource_token
            )
        else:
            sentry_logger.info(
                "Lock not obtained for outbox charge authorization task",
                extra={"task_id": self.task_id},
            )

    def outbox_request_refund(self, payload: dict):
        amount = payload.get("amount")
        currency = payload.get("currency")
        reference = payload.get("reference")
        refund_id = payload.get("refund_id")
        customer_note = payload.get("customer_note")
        merchant_note = payload.get("merchant_note")

        resource_token = str(uuid4())
        resource = self._redis_repo.access_resource_sync(
            f"refund:{refund_id}:request", resource_token
        )

        if resource:
            self._task_refund.request_refund(
                amount, currency, refund_id, reference, customer_note, merchant_note
            )

            self._redis_repo.release_lock_sync(
                f"refund:{refund_id}:request", resource_token
            )
        else:
            sentry_logger.info(
                "Lock not obtained for outbox request refund task",
                extra={"task_id": self.task_id},
            )

    def outbox_retry_refund(self, payload: dict):
        bank_id = payload.get("bank_id")
        currency = payload.get("currency")
        refund_id = payload.get("refund_id")
        account_number = payload.get("account_number")
        existing_refund_id = payload.get("existing_refund_id")

        resource_token = str(uuid4())
        resource = self._redis_repo.access_resource_sync(
            f"refund:{refund_id}:retry", resource_token
        )

        if resource:
            self._task_refund.retry_refund(
                bank_id, refund_id, existing_refund_id, currency, account_number
            )

            self._redis_repo.release_lock_sync(
                f"refund:{refund_id}:retry", resource_token
            )
        else:
            sentry_logger.info(
                "Lock not obtained for outbox retry refund task",
                extra={"task_id": self.task_id},
            )

    def outbox_webhook_event(self, payload: dict):
        message_id = payload.get("message_id")

        resource_token = str(uuid4())
        resource = self._redis_repo.access_resource_sync(
            f"webhook:{message_id}", resource_token
        )

        if resource:
            self._task_webhook._forward_to_webhook_event(payload)
            self._redis_repo.release_lock_sync(f"webhook:{message_id}", resource_token)
        else:
            sentry_logger.info(
                "Lock not obtained for outbox webhook event task",
                extra={"task_id": self.task_id},
            )

    def process_outbox_task(self):
        try:
            outbox_records = self._outbox_service._get_outbox_records(status="pending")

            updated_records = []
            for outbox in outbox_records:
                if outbox.event_type == "charge_authorization":
                    self.outbox_charge_authorization(outbox.payload)
                elif outbox.event_type == "request_refund":
                    self.outbox_request_refund(outbox.payload)
                elif outbox.event_type == "retry_refund":
                    self.outbox_retry_refund(outbox.payload)
                elif outbox.event_type == "webhook":
                    self.outbox_webhook_event(outbox.payload)

                outbox.status = "completed"
                outbox.processed_at = datetime.now(timezone)
                updated_records.append(OutBoxInDB.model_validate(outbox))

            self._outbox_service._update_outbox_records(updated_records)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing outbox rows",
                extra={"task_id": self.task_id},
            )

            raise exc
