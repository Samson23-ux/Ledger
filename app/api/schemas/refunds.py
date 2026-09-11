from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, ConfigDict


from app.api.models.enum import RefundStatus
from app.api.models.enum import CurrencyEnum


class RefundBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_transaction_id: UUID
    amount: Decimal
    currency: CurrencyEnum
    customer_note: str
    merchant_note: str
    wallet_debited: bool = False


class RefundCreate(RefundBase):
    pass


class RetryRefund(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    account_number: str
    bank_id: str


class RefundResponse(BaseModel):
    id: UUID
    payment_transaction_id: UUID
    paystack_refund_id: str
    amount: Decimal
    currency: CurrencyEnum
    status: RefundStatus
    customer_note: str
    merchant_note: str
    wallet_debited: bool = False
    refunded_at: datetime
    created_at: datetime
    updated_at: datetime
