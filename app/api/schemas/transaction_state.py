from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import SourceEnum
from app.api.models.enum import TransactionStatus


class TransactionStateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: UUID
    to_status: TransactionStatus
    source: SourceEnum


class TransactionStateCreate(TransactionStateBase):
    pass


class TransactionStateResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    from_status: TransactionStatus
    to_status: TransactionStatus
    source: SourceEnum
    occurred_at: datetime
