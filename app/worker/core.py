from httpx import Client, Limits


from app.core.config import get_settings
from app.api.repo.otp import OtpRepository
from app.api.services.otp import OtpService
from app.api.repo.email import EmailRepository
from app.api.repo.redis import RedisRepository
from app.api.services.email import EmailService
from app.worker import get_db_session, get_redis_client

SETTINGS = get_settings()


def get_redis_repo() -> RedisRepository:
    redis = next(get_redis_client())
    return RedisRepository(sync_redis=redis)


def get_email_service() -> EmailService:
    session = next(get_db_session())

    email_service: EmailService = EmailService(
        email_repo=EmailRepository(sync_session=session)
    )

    return email_service


def get_otp_service() -> OtpService:
    session = next(get_db_session())
    otp_service: OtpService = OtpService(
        otp_repo=OtpRepository(sync_session=session),
    )
    return otp_service


def raise_for_status_5xx(response):
    return response.raise_for_status()


def http_client() -> Client:
    limits = Limits(
        max_connections=100,
        max_keepalive_connections=50,
        keepalive_expiry=60 * 5,
    )
    return Client(
        timeout=10,
        limits=limits,
        event_hooks={"response": [raise_for_status_5xx]},
    )
