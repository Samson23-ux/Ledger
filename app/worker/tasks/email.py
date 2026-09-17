import secrets
import psycopg2
from uuid import UUID
from celery.exceptions import Reject
from resend.exceptions import ResendError
from datetime import datetime, timezone, timedelta

from app.worker import celery_app
from app.api.models.email import Email
from app.core.config import get_settings
from app.api.schemas.auth import OtpInDB
from app.worker import BaseTaskWithFailure
from app.core.exceptions import MaxRetriesError

SETTINGS = get_settings()
SENDER_EMAIL = SETTINGS.API_EMAIL
RESEND_API_KEY = SETTINGS.RESEND_API_KEY


@celery_app.task(base=BaseTaskWithFailure, bind=True)
def send_email(
    self,
    email_message: str,
    email_id: UUID,
    recipient_email: str,
):
    from app.worker import get_redis_repo, get_email_service

    try:
        redis_repo = get_redis_repo()
        email_service = get_email_service()

        key: str = f"idempotency:{email_id}"
        already_processed: str | None = redis_repo.get_idempotency_key(key)

        if not already_processed:
            email_service.api_key = RESEND_API_KEY
            email_service.send(
                SENDER_EMAIL,
                recipient_email,
                "Email Verification Code",
                email_message,
            )

            redis_repo.mark_idempotency_key(key, "1", SETTINGS.IDEMPOTENCY_KEY_TTL)

            email: Email = email_service.get_processed_email(email_id)
            email.status = "delivered"
            email.delivered_at = datetime.now(timezone.utc)
            email_service.update_processed_email(email)
    except (
        ResendError,
        psycopg2.OperationalError,
        psycopg2.InterfaceError,
        psycopg2.extensions.TransactionRollbackError,
    ) as exc:
        """retry for transient errors"""
        try:
            if isinstance(exc, ResendError):
                if hasattr(exc, "code") and exc.code >= 500:
                    raise self.retry(
                        exc=MaxRetriesError(str(exc)),
                        countdown=self._backoff_countdown(),
                    )
            raise self.retry(
                exc=MaxRetriesError(str(exc)), countdown=self._backoff_countdown()
            )
        except MaxRetriesError as exc:
            self._handle_failure(self.request.kwargs)
            raise Reject(exc, requeue=False)
    except Exception as exc:
        self._handle_failure(self.request.kwargs)
        raise Reject(exc, requeue=False)
