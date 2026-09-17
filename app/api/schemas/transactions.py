from uuid import UUID
from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


from app.api.models.enum import TransactionStatus
from app.api.models.enum import ChannelEnum, CurrencyEnum


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


class TransactionInDB(TransactionBase):
    currency: CurrencyEnum
    status: TransactionStatus
    gateway_response: Optional[str] = None
    authorization_code: Optional[str] = None
    bank_transfer_account_number: Optional[str] = None
    card_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    wallet_credited: bool
    created_at: datetime
    updated_at: datetime


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
    card_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    wallet_credited: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
