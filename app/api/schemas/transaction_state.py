from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import SourceEnum
from app.api.models.enum import TransactionStatus


class TransactionStateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: UUID
    status: TransactionStatus
    source: SourceEnum


class TransactionStateCreate(TransactionStateBase):
    pass


class TransactionStateInDB(TransactionStateBase):
    id: UUID
    occurred_at: datetime


class TransactionStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    status: TransactionStatus
    source: SourceEnum
    occurred_at: datetime
