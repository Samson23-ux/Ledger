import psycopg2
import sentry_sdk
from uuid import uuid4
from celery.exceptions import Reject
import sentry_sdk.logger as sentry_logger


from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.tasks.email import send_email
from app.core.exceptions import MaxRetriesError
from app.worker.tasks.base import BaseTaskWithFailure
from app.worker.core import get_redis_repo, get_db_session

SETTINGS = get_settings()


@celery_app.task(bind=True, base=BaseTaskWithFailure)
def process_webhook_events(self, out_box_id: str, payload: dict):
    try:
        from app.worker.services.webhooks import TaskWebhook

        task_id = self.request.id

        redis_repo = get_redis_repo()
        session = next(get_db_session())

        task_webhook = TaskWebhook(task_id, session)

        message_id = payload.get("message_id")

        resource_token = str(uuid4())
        resource = redis_repo.access_resource_sync(
            f"webhook:{message_id}:task", resource_token
        )  # acquire resource with redis lock

        # idempotency check against retries
        idempotency_key = redis_repo.get_idempotency_key(f"webhook:{message_id}")

        if resource and not idempotency_key:
            email_payload = task_webhook._forward_to_webhook_event(payload, out_box_id)
            session.commit()

            if email_payload:
                send_email.apply_async(priority=3, kwargs=email_payload)

            redis_repo.release_lock_sync(f"webhook:{message_id}:task", resource_token)
            redis_repo.mark_idempotency_key(
                f"webhook:{message_id}", "1", SETTINGS.IDEMPOTENCY_KEY_TTL
            )

        if not resource:
            sentry_logger.info(
                "Lock not obtained for webhook events task",
                extra={"task_id": task_id},
            )
    except (
        psycopg2.InternalError,
        psycopg2.InterfaceError,
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
