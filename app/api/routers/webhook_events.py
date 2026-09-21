from fastapi import APIRouter, Request


from app.deps import SecurityDep, WebhookEventServiceDep, UnitOfWorkRepo, read_limiter

router = APIRouter()


@router.post(
    "/webhooks/paystack",
    status_code=200,
    description="A webhook endpoint to listen for paystack events",
    dependencies=[read_limiter],
)
async def receive_webhook_events(
    request: Request,
    uow: UnitOfWorkRepo,
    security: SecurityDep,
    webhook_service: WebhookEventServiceDep,
):
    payload: dict = await request.json()
    raw_body: bytes = await request.body()
    webhook_signature = request.headers.get("x-paystack-signature")

    await webhook_service.process_webhook_event(
        security, webhook_signature, raw_body, payload, uow
    )
