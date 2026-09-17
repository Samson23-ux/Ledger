from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict


class WebhookEventBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paystack_data_id: Optional[int] = None
    paystack_reference: Optional[str] = None
    event_type: str
    payload: dict
    signature_verified: bool


class WebhookEventCreate(WebhookEventBase):
    pass
