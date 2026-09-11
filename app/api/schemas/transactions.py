from uuid import UUID
from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


from app.api.models.enum import ChannelEnum
from app.api.models.enum import TransactionStatus


class TransactionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idempotency_key: str
    user_id: UUID
    wallet_id: UUID
    paystack_reference: Optional[str] = None
    amount: Decimal
    channel: ChannelEnum


class TransactionCreate(TransactionBase):
    authorization_code: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING


class TransactionUpdate(BaseModel):
    idempotency_key: Optional[str] = None
    user_id: Optional[UUID] = None
    wallet_id: Optional[UUID] = None
    paystack_reference: Optional[str] = None
    amount: Optional[Decimal] = None
    channel: Optional[ChannelEnum] = None
    status: Optional[TransactionStatus] = None
    gateway_response: Optional[str] = None
    authorization_code: Optional[str] = None
    bank_transfer_account_number: Optional[str] = None
    bank_transfer_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    wallet_credited: Optional[bool] = None
    updated_at: Optional[datetime] = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idempotency_key: str
    user_id: UUID
    wallet_id: UUID
    paystack_reference: Optional[str] = None
    amount: Decimal = Field(max_digits=10, decimal_places=2)
    channel: ChannelEnum
    status: TransactionStatus
    status: TransactionStatus
    gateway_response: Optional[str] = None
    authorization_code: Optional[str] = None
    bank_transfer_account_number: Optional[str] = None
    bank_transfer_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    wallet_credited: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
