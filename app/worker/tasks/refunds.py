import psycopg2
import sentry_sdk
from uuid import uuid4
from celery.exceptions import Reject
import sentry_sdk.logger as sentry_logger
from paystack import exceptions as PaystackException


from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.core.exceptions import MaxRetriesError
from app.worker.tasks.base import BaseTaskWithFailure
from app.worker.core import get_redis_repo, get_db_session

SETTINGS = get_settings()


@celery_app.task(bind=True, base=BaseTaskWithFailure)
def request_refund(
    self,
    out_box_id: str,
    amount: str,
    currency: str,
    refund_id: str,
    reference: str,
    message_id: str,
    customer_note: str,
    merchant_note: str,
):
    try:
        from app.worker.services.transactions import TaskRefund

        task_id = self.request.id

        redis_repo = get_redis_repo()
        session = next(get_db_session())

        task_refund = TaskRefund(task_id, session)

        resource_token = str(uuid4())
        resource = redis_repo.access_resource_sync(
            f"refund:{refund_id}:request", resource_token
        )  # acquire resource with redis lock

        # idempotency check against retries
        idempotency_key = redis_repo.get_idempotency_key(f"refund:{message_id}:request")

        if resource and not idempotency_key:
            task_refund.request_refund(
                amount,
                currency,
                refund_id,
                reference,
                customer_note,
                merchant_note,
                out_box_id,
            )
            session.commit()

            redis_repo.release_lock_sync(f"refund:{refund_id}:request", resource_token)
            redis_repo.mark_idempotency_key(
                f"refund:{message_id}:request", "1", SETTINGS.IDEMPOTENCY_KEY_TTL
            )

        if not resource:
            sentry_logger.info(
                "Lock not obtained for request refund task",
                extra={"task_id": task_id},
            )
    except (
        psycopg2.InternalError,
        psycopg2.InterfaceError,
        PaystackException.ServiceException,
        psycopg2.extensions.TransactionRollbackError,
    ) as exc:
        try:
            session.rollback()

            raise self.retry(
                exc=MaxRetriesError(str(exc)), countdown=self._backoff_countdown()
            )
        except MaxRetriesError as exc:
            session.rollback()

            sentry_sdk.capture_exception(exc)
            raise Reject(reason=exc)
    except Exception as exc:
        session.rollback()

        sentry_sdk.capture_exception(exc)
        raise Reject(reason=exc)


@celery_app.task(bind=True, base=BaseTaskWithFailure)
def retry_refund(
    self,
    out_box_id: str,
    currency: str,
    refund_id: str,
    existing_refund_id: int,
    message_id: str,
    account_number: str,
    bank_id: str,
):
    try:
        from app.worker.services.transactions import TaskRefund

        task_id = self.request.id

        redis_repo = get_redis_repo()
        session = next(get_db_session())

        task_refund = TaskRefund(task_id, session)

        resource_token = str(uuid4())
        resource = redis_repo.access_resource_sync(
            f"refund:{refund_id}:retry", resource_token
        )  # acquire resource with redis lock

        # idempotency check against retries
        idempotency_key = redis_repo.get_idempotency_key(f"refund:{message_id}:retry")

        if resource and not idempotency_key:
            task_refund.retry_refund(
                bank_id,
                refund_id,
                existing_refund_id,
                currency,
                account_number,
                out_box_id,
            )
            session.commit()

            redis_repo.release_lock_sync(f"refund:{refund_id}:retry", resource_token)
            redis_repo.mark_idempotency_key(
                f"refund:{message_id}:retry", "1", SETTINGS.IDEMPOTENCY_KEY_TTL
            )

        if not resource:
            sentry_logger.info(
                "Lock not obtained for retry refund task",
                extra={"task_id": task_id},
            )
    except (
        psycopg2.InternalError,
        psycopg2.InterfaceError,
        PaystackException.ServiceException,
        psycopg2.extensions.TransactionRollbackError,
    ) as exc:
        try:
            session.rollback()

            raise self.retry(
                exc=MaxRetriesError(str(exc)), countdown=self._backoff_countdown()
            )
        except MaxRetriesError as exc:
            session.rollback()

            sentry_sdk.capture_exception(exc)
            raise Reject(reason=exc)
    except Exception as exc:
        session.rollback()

        sentry_sdk.capture_exception(exc)
        raise Reject(reason=exc)
