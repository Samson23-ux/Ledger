import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import BIGINT
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
)


from app.api.models.base import Base
from app.api.models.state import RefundStatus
from app.api.models.wallets import CurrencyEnum


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    payment_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "payment_transactions.id",
            ondelete="CASCADE",
            name="wallet_credits_payment_transaction_id_fk",
        ),
    )
    paystack_refund_id: Mapped[str | None] = mapped_column(Text, unique=True)
    amount: Mapped[int] = mapped_column(BIGINT)
    currency: Mapped[enum.Enum] = mapped_column(
        Enum(CurrencyEnum, values_callable=lambda e: [m.value for m in e]),
        default=CurrencyEnum.NGN,
    )
    status: Mapped[enum.Enum] = mapped_column(
        Enum(RefundStatus, values_callable=lambda e: [m.value for m in e]),
        default=RefundStatus.PENDING,
    )
    customer_note: Mapped[str | None] = mapped_column(Text)
    merchant_note: Mapped[str | None] = mapped_column(Text)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wallet_debited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="refunds_pk"),
        Index("idx_refunds_payment_transaction_id_&_id", payment_transaction_id, id),
        Index("idx_refunds_created_at", created_at),
        Index("idx_refunds_updated_at", updated_at)
    )
