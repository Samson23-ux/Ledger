from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import SourceEnum
from app.api.models.enum import RefundStatus


class RefundStateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    refund_id: UUID
    status: RefundStatus
    source: SourceEnum


class RefundStateCreate(RefundStateBase):
    pass


class RefundStateInDB(RefundStateBase):
    id: UUID
    occurred_at: datetime


class RefundStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    refund_id: UUID
    status: RefundStatus
    source: SourceEnum
    occurred_at: datetime
