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
from app.worker.services.transactions import TaskTransaction

SETTINGS = get_settings()


@celery_app.task(bind=True, base=BaseTaskWithFailure)
def charge_authorization(
    self,
    out_box_id: str,
    email: str,
    amount: str,
    currency: str,
    message_id: str,
    transaction_id: str,
    authorization_code: str,
):
    try:
        task_id = self.request.id

        redis_repo = get_redis_repo()
        session = next(get_db_session())

        task_transaction = TaskTransaction(task_id, session)

        resource_token = str(uuid4())
        resource = redis_repo.access_resource_sync(
            f"charge:{transaction_id}", resource_token
        )  # acquire resource with redis lock

        # idempotency check against retries
        idempotency_key = redis_repo.get_idempotency_key(f"charge:{message_id}")

        if resource and not idempotency_key:
            task_transaction.charge_authorization(
                email, amount, currency, authorization_code, transaction_id, out_box_id
            )
            session.commit()

            redis_repo.release_lock_sync(f"charge:{transaction_id}", resource_token)
            redis_repo.mark_idempotency_key(
                f"charge:{message_id}", "1", SETTINGS.IDEMPOTENCY_KEY_TTL
            )

        if not resource:
            sentry_logger.info(
                "Lock not obtained for charge authorization task",
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
