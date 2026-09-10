from uuid import UUID
from pydantic import BaseModel, ConfigDict


class WebhookEventBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paystack_data_id: str
    paystack_reference: str
    event_type: str
    payload: dict
    signature_verified: bool


class WebhookEventCreate(WebhookEventBase):
    pass
