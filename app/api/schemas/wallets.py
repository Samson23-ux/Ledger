from uuid import UUID
from decimal import Decimal
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


from app.api.models.enum import ChannelEnum
from app.api.models.enum import CurrencyEnum


class WalletBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID


class WalletCreate(WalletBase):
    balance: Decimal
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class WalletFund(BaseModel):
    channel: ChannelEnum
    amount: Decimal = Field(decimal_places=2, max_digits=10)


class WalletResponse(WalletBase):
    id: UUID
    balance: Decimal
    currency: CurrencyEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
