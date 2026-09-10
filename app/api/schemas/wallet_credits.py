from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class WalletCreditBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: UUID
    payment_transaction_id: UUID
    amount: Decimal


class WalletCreditCreate(WalletCreditBase):
    pass


class WalletCreditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wallet_id: UUID
    payment_transaction_id: UUID
    amount: Decimal
    created_at: datetime
