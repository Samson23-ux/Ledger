from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.outbox import OutBoxEnum


class OutBoxBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    payload: dict


class OutBoxCreate(OutBoxBase):
    pass


class OutBoxUpdate(BaseModel):
    status: Optional[OutBoxEnum] = None
    processed_at: Optional[datetime] = None
