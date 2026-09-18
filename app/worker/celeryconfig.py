from kombu import Queue
from celery.schedules import crontab


task_acks_late = True
worker_concurrency = 100
timezone = "Africa/Lagos"
reject_on_worker_lost = True
worker_prefetch_multiplier = 1

queue_arguments = {
    "x-max-priority": 10,
    "x-dead-letter-routing-key": "dlq",
    "x-dead-letter-exchange": "ledger.dlx",
}

task_queues = (
    Queue("ledger.dlq", "ledger.dlx", "dlq"),
    Queue("ledger.beat", "ledger.direct", "beat", queue_arguments=queue_arguments),
    Queue("ledger.celery", "ledger.direct", "celery", queue_arguments=queue_arguments),
)

task_routes = {
    "app.worker.tasks.email.send_email": {"queue": "ledger.celery"},
    "app.worker.tasks.outbox.outbox_task": {"queue": "ledger.beat"},
    "app.worker.tasks.refunds.retry_refund": {"queue": "ledger.celery"},
    "app.worker.tasks.refunds.request_refund": {"queue": "ledger.celery"},
    "app.worker.tasks.reconcile_refund.reconcile_refund": {"queue": "ledger.beat"},
    "app.worker.tasks.webhook_events.process_webhook_events": {"queue": "ledger.celery"},
    "app.worker.tasks.charge_authorization.charge_authorization": {"queue": "ledger.celery"},
    "app.worker.tasks.reconcile_transaction.reconcile_transaction": {"queue": "ledger.beat"},
}


beat_schedule = {
    "transc_task": {
        "task": "app.worker.tasks.reconcile_transaction.reconcile_transaction",
        "schedule": crontab(minute="*/3")
    },
    "refund_task": {
        "task": "app.worker.tasks.reconcile_refund.reconcile_refund",
        "schedule": crontab(minute="*/3")
    },
    "outbox_task": {
        "task": "app.worker.tasks.outbox.outbox_task",
        "schedule": crontab(minute="*/5")
    }
}
