from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import SourceEnum
from app.api.models.enum import RefundStatus


class RefundStateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    refund_id: UUID
    to_status: RefundStatus
    source: SourceEnum


class RefundStateCreate(RefundStateBase):
    pass


class RefundStateResponse(BaseModel):
    id: UUID
    refund_id: UUID
    from_status: RefundStatus
    to_status: RefundStatus
    source: SourceEnum
    occurred_at: datetime
