import sentry_sdk
from uuid import uuid7
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import sentry_sdk.logger as sentry_logger


from app.worker.core import http_client
from app.core.config import get_settings
from app.worker.tasks.email import send_email
from app.api.schemas.refunds import RefundInDB
from app.api.repo.refunds import RefundRepository
from app.api.services.refunds import RefundService
from app.api.services.thread_pool import ThreadPool
from app.worker.services.webhooks import TaskWebhook
from app.api.schemas.refund_state import RefundStateInDB
from app.api.schemas.transactions import TransactionInDB
from app.api.repo.transactions import TransactionRepository
from app.api.repo.refund_state import RefundStateRepository
from app.api.services.transactions import TransactionService
from app.api.services.payment_gateway import Transaction, Refund
from app.api.repo.transaction_state import TransactionStateRepository
from app.api.services.transaction_state import TransactionStateService
from app.api.services.refund_state import RefundStateService, RefundStateCreate
from app.api.schemas.transaction_state import (
    TransactionStateInDB,
    TransactionStateCreate,
)
from app.email_texts import (
    refund_failed_message,
    refund_processed_message,
    failed_transaction_message,
    rejected_transaction_message,
    successful_transaction_message,
    refund_needs_attention_message,
)

SETTINGS = get_settings()


class ReconcileTransaction:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id
        self._session = session

        self._task_webhook = TaskWebhook(self.task_id, self._session)
        self._gateway = Transaction(
            api_key=SETTINGS.PAYSTACK_API_KEY, client=http_client()
        )

        self._transaction_service = TransactionService(
            pool=ThreadPool(),
            transaction_repo=TransactionRepository(sync_session=self._session),
        )
        self._state_service = TransactionStateService(
            state_repo=TransactionStateRepository(sync_session=self._session)
        )

    def reconciliation(self):
        try:
            transactions = self._transaction_service._get_pending_transactions(
                reconcile=True
            )

            state_updates = []
            transaction_updates = []

            for transaction in transactions:
                user_email = transaction.user.email or transaction.user.google_email
                paystack_transaction = self._gateway.verify_transaction(
                    transaction.paystack_reference
                )

                transaction_status = payload_data["status"]
                payload_data = paystack_transaction["data"]

                if transaction_status == "success":
                    payload = {
                        "event": "charge.success",
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

                    transaction, state_create = (
                        self._task_webhook._process_success_event(transaction, payload)
                    )

                    email_message = successful_transaction_message(
                        transaction.amount,
                        transaction.currency,
                        transaction.paystack_reference,
                    )
                    send_email.apply_async(
                        priority=3,
                        kwargs={
                            "email_message": email_message,
                            "email_id": str(uuid7()),
                            "recipient_email": user_email,
                        },
                    )
                elif (
                    transaction.status == "reversed"
                    or transaction.status == "reversal_pending"
                ):
                    continue
                else:
                    transaction.status = transaction_status
                    transaction.updated_at = datetime.now(timezone.utc)
                    transaction.gateway_response = payload.get("gateway_response")
                    transaction.authorization_code = payload.get("authorization_code")

                    if transaction_status == "rejected":
                        email_message = rejected_transaction_message(
                            transaction.amount,
                            transaction.currency,
                            transaction.paystack_reference,
                        )
                        send_email.apply_async(
                            priority=3,
                            kwargs={
                                "email_message": email_message,
                                "email_id": str(uuid7()),
                                "recipient_email": user_email,
                            },
                        )
                    elif transaction_status == "failed":
                        email_message = failed_transaction_message(
                            transaction.amount,
                            transaction.currency,
                            transaction.paystack_reference,
                        )
                        send_email.apply_async(
                            priority=3,
                            kwargs={
                                "email_message": email_message,
                                "email_id": str(uuid7()),
                                "recipient_email": user_email,
                            },
                        )

                    state_create: TransactionStateCreate = TransactionStateCreate(
                        transaction_id=transaction.id,
                        status=transaction_status,
                        source="reconciliation",
                    )

                state_updates.append(TransactionStateInDB.model_validate(state_create))
                transaction_updates.append(TransactionInDB.model_validate(transaction))

            if transactions:
                self._state_service._create_state_records(state_updates)
                self._transaction_service._update_transaction_records(transaction_updates)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while checking transaction state from paystack in task",
                extra={"task_id": self.task_id},
            )

            raise exc


class ReconcileRefund:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id
        self._session = session

        self._task_webhook = TaskWebhook(self.task_id, self._session)
        self._gateway = Refund(api_key=SETTINGS.PAYSTACK_API_KEY, client=http_client())

        self._refund_service = RefundService(
            pool=ThreadPool(), refund_repo=RefundRepository(sync_session=self._session)
        )
        self._state_service = RefundStateService(
            state_repo=RefundStateRepository(sync_session=self._session)
        )

    def reconciliation(self):
        try:
            refunds = self._refund_service._get_pending_refunds(reconcile=True)

            state_updates = []
            refunds_updates = []

            for refund in refunds:
                user_email = refund.user.email or refund.user.google_email
                paystack_refund = self._gateway.get_refund(refund.paystack_refund_id)

                refund_status = paystack_refund["data"]["status"]

                if refund_status == "processed":
                    refund, state_create = self._task_webhook._refund_processed(
                        refund.transaction, refund
                    )

                    email_message = refund_processed_message(
                        refund.amount,
                        refund.currency,
                        refund.transaction.paystack_reference,
                    )
                    send_email.apply_async(
                        priority=3,
                        kwargs={
                            "email_message": email_message,
                            "email_id": str(uuid7()),
                            "recipient_email": user_email,
                        },
                    )
                else:
                    refund.status = refund_status
                    refund.updated_at = datetime.now(timezone.utc)

                    state_create: RefundStateCreate = RefundStateCreate(
                        refund_id=refund.id,
                        status=refund_status,
                        source="reconciliation",
                    )

                    refunds_updates.append(RefundInDB.model_validate(refund))
                    state_updates.append(RefundStateInDB.model_validate(state_create))

                    if refund_status == "needs-attention":
                        email_message = refund_needs_attention_message(
                            refund.amount,
                            refund.currency,
                            refund.transaction.paystack_reference,
                        )
                        send_email.apply_async(
                            priority=3,
                            kwargs={
                                "email_message": email_message,
                                "email_id": str(uuid7()),
                                "recipient_email": user_email,
                            },
                        )
                    elif refund_status == "failed":
                        email_message = refund_failed_message(
                            refund.amount,
                            refund.currency,
                            refund.transaction.paystack_reference,
                        )
                        send_email.apply_async(
                            priority=3,
                            kwargs={
                                "email_message": email_message,
                                "email_id": str(uuid7()),
                                "recipient_email": user_email,
                            },
                        )

            if refunds:
                self._state_service._create_state_records(state_updates)
                self._refund_service._update_refund_records(refunds_updates)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while checking refund state from paystack in task",
                extra={"task_id": self.task_id},
            )

            raise exc
