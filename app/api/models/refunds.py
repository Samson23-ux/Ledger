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
    Numeric,
    BigInteger,
    PrimaryKeyConstraint,
)


from app.api.models.base import Base
from app.api.models.enum import RefundStatus
from app.api.models.enum import CurrencyEnum


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE", name="refunds_user_id_fk"),
    )
    payment_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "payment_transactions.id",
            ondelete="CASCADE",
            name="wallet_credits_payment_transaction_id_fk",
        ),
    )
    paystack_refund_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, default=None
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2))
    currency: Mapped[enum.Enum] = mapped_column(
        Enum(CurrencyEnum, values_callable=lambda e: [m.value for m in e]),
        default=CurrencyEnum.NGN,
    )
    status: Mapped[enum.Enum] = mapped_column(
        Enum(RefundStatus, values_callable=lambda e: [m.value for m in e]),
        default=RefundStatus.PENDING,
    )
    customer_note: Mapped[str | None] = mapped_column(Text, default=None)
    merchant_note: Mapped[str | None] = mapped_column(Text, default=None)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    wallet_debited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user = relationship("User", viewonly=True, lazy="selectin")
    transaction = relationship("PaymentTransaction", viewonly=True, lazy="selectin")

    __table_args__ = (
        PrimaryKeyConstraint("id", name="refunds_pk"),
        Index("idx_refunds_composite", user_id, id, status),
        Index("idx_refunds_created_at", created_at),
        Index("idx_refunds_updated_at", updated_at),
        Index("idx_refunds_payment_transaction_id_&_id", payment_transaction_id, id),
    )
