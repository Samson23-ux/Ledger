import sentry_sdk
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import sentry_sdk.logger as sentry_logger


from app.worker.core import http_client
from app.core.config import get_settings
from app.api.repo.outbox import OutBoxRepository
from app.api.repo.refunds import RefundRepository
from app.api.services.outbox import OutBoxService
from app.api.services.refunds import RefundService
from app.api.services.thread_pool import ThreadPool
from app.api.schemas.refund_state import RefundStateCreate
from app.api.repo.transactions import TransactionRepository
from app.api.repo.refund_state import RefundStateRepository
from app.api.services.transactions import TransactionService
from app.api.services.refund_state import RefundStateService
from app.api.services.payment_gateway import Transaction, Refund
from app.api.schemas.transaction_state import TransactionStateCreate
from app.api.repo.transaction_state import TransactionStateRepository
from app.api.services.transaction_state import TransactionStateService

SETTINGS = get_settings()


class TaskTransaction:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id
        self._session = session

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
        self._out_box_service = OutBoxService(
            out_box_repo=OutBoxRepository(sync_session=self._session)
        )

    def charge_authorization(
        self,
        email: str,
        amount: str,
        currency: str,
        authorization_code: str,
        transaction_id: str,
        out_box_id: str,
    ):
        try:
            transaction = self._transaction_service._get_transaction_sync(
                id=transaction_id
            )

            if transaction:
                res = self._gateway.charge_authorization(
                    email, amount, currency, authorization_code
                )

                transaction.status = "initiated"
                transaction.paystack_reference = res["data"]["reference"]
                transaction.updated_at = datetime.now(timezone.utc)

                state_create: TransactionStateCreate = TransactionStateCreate(
                    transaction_id=transaction.id,
                    status="initiated",
                    source="user_action",
                )

                self._transaction_service._update_transaction_sync(transaction)
                self._state_service._create_transaction_state_sync(state_create)
                self._out_box_service.mark_processed_sync(out_box_id)

                sentry_logger.info(
                    "Transaction charged successfully", extra={"task_id": self.task_id}
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while charging authorization in task",
                extra={"task_id": self.task_id},
            )

            raise exc


class TaskRefund:
    def __init__(self, task_id: str, session: Session):
        self.task_id = task_id

        self._session = session
        self._gateway = Refund(api_key=SETTINGS.PAYSTACK_API_KEY, client=http_client())

        self._refund_service = RefundService(
            pool=ThreadPool(), refund_repo=RefundRepository(sync_session=self._session)
        )
        self._state_service = RefundStateService(
            state_repo=RefundStateRepository(sync_session=self._session)
        )
        self._out_box_service = OutBoxService(
            out_box_repo=OutBoxRepository(sync_session=self._session)
        )

    def request_refund(
        self,
        amount: str,
        currency: str,
        refund_id: str,
        reference: str,
        customer_note: str,
        merchant_note: str,
        out_box_id: str,
    ):
        try:
            refund = self._refund_service._get_refund_sync(id=refund_id)

            if refund:
                res = self._gateway.request_refund(
                    reference, amount, currency, customer_note, merchant_note
                )

                refund.status = "initiated"
                refund.paystack_refund_id = res["data"]["id"]
                refund.updated_at = datetime.now(timezone.utc)

                state_create = RefundStateCreate(
                    refund_id=refund_id,
                    status="initiated",
                    source="user_action",
                )

                self._refund_service._update_refund_sync(refund)
                self._state_service._create_refund_state_sync(state_create)
                self._out_box_service.mark_processed_sync(out_box_id)

                sentry_logger.info(
                    "Refund requested charged successfully", extra={"task_id": self.task_id}
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while requesting for refund in task",
                extra={"task_id": self.task_id},
            )

            raise exc

    def retry_refund(
        self,
        bank_id: str,
        refund_id: str,
        existing_refund_id: str,
        currency: str,
        account_number: str,
        out_box_id: str,
    ):
        try:
            refund = self._refund_service._get_refund_sync(id=refund_id)

            if refund:
                res = self._gateway.retry_refund(
                    existing_refund_id, currency, account_number, bank_id
                )

                refund.status = "initiated"
                refund.paystack_refund_id = res["data"]["id"]
                refund.updated_at = datetime.now(timezone.utc)

                state_create = RefundStateCreate(
                    refund_id=refund_id,
                    status="initiated",
                    source="user_action",
                )

                self._refund_service._update_refund_sync(refund)
                self._state_service._create_refund_state_sync(state_create)
                self._out_box_service.mark_processed_sync(out_box_id)

                sentry_logger.info(
                    "Refund retried successfully", extra={"task_id": self.task_id}
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrying for refund in task",
                extra={"task_id": self.task_id},
            )

            raise exc
