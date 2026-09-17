import sentry_sdk
from uuid import uuid7
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import sentry_sdk.logger as sentry_logger


from app.worker.core import http_client
from app.core.config import get_settings
from app.api.models.refunds import Refund
from app.worker.tasks.email import send_email
from app.api.repo.refunds import RefundRepository
from app.api.services.refunds import RefundService
from app.api.services.thread_pool import ThreadPool
from app.api.services.payment_gateway import Transaction
from app.api.models.transactions import PaymentTransaction
from app.api.schemas.refund_state import RefundStateCreate
from app.api.repo.refund_state import RefundStateRepository
from app.api.repo.transactions import TransactionRepository
from app.api.services.transactions import TransactionService
from app.api.services.refund_state import RefundStateService
from app.api.repo.authorization_codes import AuthCodeRepository
from app.api.schemas.authorization_codes import AuthCodesCreate
from app.api.services.authorization_codes import AuthCodeService
from app.api.schemas.transaction_state import TransactionStateCreate
from app.api.repo.transaction_state import TransactionStateRepository
from app.api.services.transaction_state import TransactionStateService
from app.email_texts import (
    refund_failed_message,
    refund_processed_message,
    rejected_transaction_message,
    successful_transaction_message,
    refund_needs_attention_message,
)

SETTINGS = get_settings()


class TaskWebhook:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id
        self._session = session

        self._refund_service = RefundService(
            pool=ThreadPool(), refund_repo=RefundRepository(sync_session=self._session)
        )
        self._refund_state_service = RefundStateService(
            refund_repo=RefundStateRepository(sync_session=self._session)
        )

        self._auth_code_service = AuthCodeService(
            code_repo=AuthCodeRepository(sync_session=self._session)
        )
        self._gateway = Transaction(
            api_key=SETTINGS.PAYSTACK_API_KEY, client=http_client()
        )

        self._transaction_service = TransactionService(
            pool=ThreadPool(),
            transaction_repo=TransactionRepository(sync_session=self._session),
        )
        self._transaction_state_service = TransactionStateService(
            state_repo=TransactionStateRepository(sync_session=self._session)
        )

    def _process_success_event(self, transaction: PaymentTransaction, payload: dict):
        wallet = transaction.wallet
        wallet.balance += transaction.amount

        transaction.wallet_credited = True
        transaction.paid_at = datetime.now(timezone.utc)

        transaction.status = "success"
        transaction.card_expires_at = datetime(
            payload.get("expiry_year"),
            payload.get("expiry_month"),
            1,
            tzinfo=timezone.utc,
        )
        transaction.gateway_response = payload.get("gateway_response")

        if transaction.channel == "card":
            transaction.authorization_code = payload.get("authorization_code")

            auth_code = AuthCodesCreate(
                wallet_id=transaction.wallet_id,
                code=payload.get("authorization_code"),
                exp_month=payload.get("expiry_month"),
                exp_year=payload.get("expiry_year"),
                card_type=payload.get("card_type"),
                country_code=payload.get("country_code"),
                reusable=payload.get("code_reusable"),
            )

            self._auth_code_service._create_auth_code(auth_code)
        elif transaction.channel == "bank_transfer":
            transaction.bank_transfer_account_number = payload.get(
                "sender_bank_account_number"
            )

        wallet.updated_at = datetime.now(timezone.utc)
        transaction.updated_at = datetime.now(timezone.utc)

        state_create: TransactionStateCreate = TransactionStateCreate(
            transaction_id=transaction.id,
            status="success",
            source="webhook",
        )

        return transaction, state_create

    def transaction_success_event(self, payload: dict):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=payload.get("reference")
            )

            if transaction and not transaction.wallet_credited:
                transaction, state_create = self._process_success_event(
                    transaction, payload
                )

                self._transaction_service._update_transaction_sync(transaction)
                self._transaction_state_service._create_transaction_state_sync(
                    state_create
                )

                email_message = successful_transaction_message(
                    transaction.amount, transaction.currency, transaction.paystack_reference
                )
                user_email = transaction.user.email or transaction.user.google_email

                send_email(email_message, uuid7(), user_email)

                sentry_logger.info(
                    "Transaction success event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while crediting wallet on sucessful transaction in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def transfer_reject_event(self, payload: dict):
        try:
            transaction_id = payload.get("transaction_id")

            received_transaction = self._gateway.fetch_transaction(transaction_id)

            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=received_transaction["data"]["reference"]
            )

            if transaction:
                transaction.status = "rejected"
                transaction.updated_at = datetime.now(timezone.utc)

                state_create: TransactionStateCreate = TransactionStateCreate(
                    transaction_id=transaction.id,
                    status="rejected",
                    source="webhook",
                )

                self._transaction_service._update_transaction_sync(transaction)
                self._transaction_state_service._create_transaction_state_sync(
                    state_create
                )

                email_message = rejected_transaction_message(
                    transaction.amount, transaction.currency, transaction.paystack_reference
                )
                user_email = transaction.user.email or transaction.user.google_email

                send_email(email_message, uuid7(), user_email)

                sentry_logger.info(
                    "Transaction rejected event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing rejected transaction in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def refund_processing_event(self, payload: dict):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=payload.get("reference")
            )

            refund = self._refund_service._get_refund_sync(
                payment_transaction_id=transaction.id
            )

            if refund:
                state_create = RefundStateCreate(
                    refund_id=refund.id,
                    status="processing",
                    source="webhook",
                )

                refund.status = "processing"
                refund.updated_at = datetime.now(timezone.utc)

                self._refund_service._update_refund_sync(refund)
                self._refund_state_service._create_refund_state_sync(state_create)

                sentry_logger.info(
                    "Refund processing event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing processing refund event in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def refund_needs_attention_event(self, payload: dict):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=payload.get("reference")
            )

            refund = self._refund_service._get_refund_sync(
                payment_transaction_id=transaction.id
            )

            if refund:
                state_create = RefundStateCreate(
                    refund_id=refund.id,
                    status="needs_attention",
                    source="webhook",
                )

                refund.status = "needs_attention"
                refund.updated_at = datetime.now(timezone.utc)

                self._refund_service._update_refund_sync(refund)
                self._refund_state_service._create_refund_state_sync(state_create)

                email_message = refund_needs_attention_message(
                    refund.amount, refund.currency, transaction.paystack_reference
                )
                user_email = refund.user.email or refund.user.google_email

                send_email(email_message, uuid7(), user_email)

                sentry_logger.info(
                    "Refund needs attention event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing needs attention refund event in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def _refund_processed(self, transaction: PaymentTransaction, refund: Refund):
        wallet = transaction.wallet

        wallet.balance -= refund.amount
        wallet.updated_at = datetime.now(timezone.utc)

        state_create = RefundStateCreate(
            refund_id=refund.id,
            status="processed",
            source="webhook",
        )

        refund.status = "processed"
        refund.wallet_debited = True

        refund.refunded_at = datetime.now(timezone.utc)
        refund.updated_at = datetime.now(timezone.utc)

        return refund, state_create

    def refund_processed_event(self, payload: dict):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=payload.get("reference")
            )

            refund = self._refund_service._get_refund_sync(
                payment_transaction_id=transaction.id
            )

            if refund and not refund.wallet_debited:
                refund, state_create = self._refund_processed(
                    transaction, refund
                )

                self._refund_service._update_refund_sync(refund)
                self._refund_state_service._create_refund_state_sync(state_create)

                email_message = refund_processed_message(
                    refund.amount, refund.currency, transaction.paystack_reference
                )
                user_email = refund.user.email or refund.user.google_email

                send_email(email_message, uuid7(), user_email)

                sentry_logger.info(
                    "Refund processed event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing processed refund event in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def refund_failed_event(self, payload: dict):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                paystack_reference=payload.get("reference")
            )

            refund = self._refund_service._get_refund_sync(
                payment_transaction_id=transaction.id
            )

            if refund:
                state_create = RefundStateCreate(
                    refund_id=refund.id,
                    status="failed",
                    source="webhook",
                )

                refund.status = "failed"
                refund.updated_at = datetime.now(timezone.utc)

                self._refund_service._update_refund_sync(refund)
                self._refund_state_service._create_refund_state_sync(state_create)

                email_message = refund_failed_message(
                    refund.amount, refund.currency, transaction.paystack_reference
                )
                user_email = refund.user.email or refund.user.google_email

                send_email(email_message, uuid7(), user_email)

                sentry_logger.info(
                    "Refund failed event received successfully",
                    extra={"task_id": self.task_id},
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while processing failed refund event in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def _forward_to_webhook_event(self, payload: dict):
        event = payload.get("event")

        if event == "charge.success":
            self.transaction_success_event(payload)
        elif event == "bank.transfer.rejected":
            self.transfer_reject_event(payload)
        elif event == "refund.processing":
            self.refund_processing_event(payload)
        elif event == "refund.processed":
            self.refund_processed_event(payload)
        elif event == "refund.failed":
            self.refund_failed_event(payload)
        elif event == "refund.needs-attention":
            self.refund_needs_attention_event(payload)
