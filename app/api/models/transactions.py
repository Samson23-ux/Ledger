import enum
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Index,
    ForeignKey,
    Text,
    Enum,
    Boolean,
    PrimaryKeyConstraint,
    Numeric
)


from app.api.models.base import Base
from app.api.models.enum import ChannelEnum
from app.api.models.enum import CurrencyEnum
from app.api.models.enum import TransactionStatus


class ChannelEnum(str, enum.Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "users.id", ondelete="CASCADE", name="payment_transactions_user_id_fk"
        ),
        unique=True,
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "wallets.id", ondelete="CASCADE", name="payment_transactions_wallet_id_fk"
        ),
    )
    paystack_reference: Mapped[str | None] = mapped_column(Text, unique=True, default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2))
    currency: Mapped[enum.Enum] = mapped_column(
        Enum(CurrencyEnum, values_callable=lambda e: [m.value for m in e]),
        default=CurrencyEnum.NGN,
    )
    channel: Mapped[enum.Enum] = mapped_column(
        Enum(ChannelEnum, values_callable=lambda e: [m.value for m in e]),
    )
    status: Mapped[enum.Enum] = mapped_column(
        Enum(TransactionStatus, values_callable=lambda e: [m.value for m in e]),
        default=TransactionStatus.PENDING,
    )
    gateway_response: Mapped[str | None] = mapped_column(Text, default=None)
    authorization_code: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # card-only channel
    bank_transfer_account_number: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # transfer-only channel
    card_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    wallet_credited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user = relationship("User", viewonly=True, lazy="selectin")
    wallet = relationship("Wallet", viewonly=True, lazy="selectin")

    __table_args__ = (
        PrimaryKeyConstraint("id", name="payment_transactions_pk"),
        Index("idx_payment_transactions_user_id", user_id, id),
        Index("idx_payment_transactions_wallet_id", wallet_id),
        Index(
            "idx_payment_transactions_paystack_reference",
            paystack_reference,
            unique=True,
        ),
        Index("idx_payment_transactions_status_id", status, id, unique=True),
        Index("idx_payment_transactions_created_at", created_at),
        Index("idx_payment_transactions_updated_at", updated_at),
    )
