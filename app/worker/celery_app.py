import sentry_sdk
from celery import Celery

from app.core.config import get_settings

SETTINGS = get_settings()

sentry_sdk.init(
    dsn=SETTINGS.SENTRY_SDK_DSN,
    enable_logs=True,
    send_default_pii=True,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    profile_lifecycle="trace",
)

tasks = [
    "app.worker.tasks.email",
    "app.worker.tasks.outbox",
    "app.worker.tasks.refunds",
    "app.worker.tasks.webhook_events",
    "app.worker.tasks.reconcile_refund",
    "app.worker.tasks.charge_authorization",
    "app.worker.tasks.reconcile_transaction"
]

celery_app = Celery(
    main="celery_app",
    broker=SETTINGS.BROKER_URL,
    backend=SETTINGS.REDIS_URL,
    include=tasks,
)

celery_app.config_from_object("app.worker.celeryconfig")
