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
    Queue("ledger.email", "ledger.direct", "email", queue_arguments=queue_arguments),
    Queue("ledger.transc", "ledger.direct", "transc", queue_arguments=queue_arguments),
    Queue("ledger.webhooks", "ledger.direct", "webhooks", queue_arguments=queue_arguments),
    Queue("ledger.outbox", "ledger.direct", "outbox", queue_arguments=queue_arguments),
    Queue("ledger.reconcile", "ledger.direct", "reconcile", queue_arguments=queue_arguments),
)

task_routes = {
    "app.worker.tasks.email.send_verification_email": {"queue": "ledger.email"}
}


beat_schedule = {
    "transc_task": {
        "task": "",
        "schedule": crontab(minute="*/3")
    },
    "refund_task": {
        "task": "",
        "schedule": crontab(minute="*/3")
    },
    "outbox_task": {
        "task": "",
        "schedule": crontab(minute="*/3")
    }
}
