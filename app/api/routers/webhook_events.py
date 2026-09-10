from fastapi import APIRouter, Request


from app.deps import SecurityDep, WebhookEventServiceDep

router = APIRouter()


@router.post(
    "/webhooks/paystack",
    status_code=200,
    description="A webhook endpoint to listen for paystack events",
)
async def receive_webhook_events(
    request: Request, security: SecurityDep, webhook_service: WebhookEventServiceDep
):
    payload: dict = await request.json()
    webhook_signature = request.headers.get("x-paystack-signature")

    await webhook_service.process_webhook_event(security, webhook_signature, payload)
