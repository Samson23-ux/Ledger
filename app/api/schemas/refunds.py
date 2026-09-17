from uuid import UUID
from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import RefundStatus
from app.api.models.enum import CurrencyEnum, RefundStatus


class RefundBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    payment_transaction_id: UUID
    amount: Decimal
    currency: CurrencyEnum
    customer_note: str
    merchant_note: str
    wallet_debited: bool = False


class RefundCreate(RefundBase):
    pass


class RefundInDB(RefundBase):
    paystack_refund_id: Optional[int] = None
    status: RefundStatus
    refunded_at: datetime
    created_at: datetime
    updated_at: datetime


class RetryRefund(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    account_number: str
    bank_id: str


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_transaction_id: UUID
    paystack_refund_id: Optional[int] = None
    amount: Decimal
    currency: CurrencyEnum
    status: RefundStatus
    customer_note: str
    merchant_note: str
    wallet_debited: bool = False
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
