import psycopg2
import sentry_sdk
from celery.exceptions import Reject
from paystack import exceptions as PaystackException


from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.tasks.email import send_email
from app.core.exceptions import MaxRetriesError
from app.worker.tasks.base import BaseTaskWithFailure
from app.worker.core import get_redis_repo, get_db_session
from app.worker.services.reconciliation import ReconcileTransaction

SETTINGS = get_settings()


@celery_app.task(bind=True, base=BaseTaskWithFailure)
def reconcile_transaction(self):
    try:
        task_id = self.request.id

        redis_repo = get_redis_repo()
        session = next(get_db_session())

        reconcile = ReconcileTransaction(task_id, session)

        idempotency_key = redis_repo.get_idempotency_key(
            f"reconcile:{task_id}:transaction"
        )

        if not idempotency_key:
            email_payload = reconcile.reconciliation()
            session.commit()

            if email_payload:
                send_email.apply_async(priority=3, kwargs=email_payload)

            redis_repo.mark_idempotency_key(
                f"reconcile:{task_id}:transaction", "1", SETTINGS.IDEMPOTENCY_KEY_TTL
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
