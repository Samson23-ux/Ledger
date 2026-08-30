import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy import text, UUID, DateTime, Index, ForeignKey, PrimaryKeyConstraint


from app.api.models.base import Base


class WalletCredit(Base):
    __tablename__ = "wallet_credits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "wallets.id", ondelete="CASCADE", name="wallet_credits_wallet_id_fk"
        ),
    )
    payment_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "payment_transactions.id",
            ondelete="CASCADE",
            name="wallet_credits_payment_transaction_id_fk",
        ),
        unique=True,
    )
    amount: Mapped[int] = mapped_column(BIGINT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="wallet_credits_pk"),
        Index("idx_wallet_credits_wallet_id", wallet_id),
        Index(
            "idx_wallet_credits_payment_transaction_id",
            payment_transaction_id,
            unique=True,
        ),
    )
