import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    Index,
)

from app.api.models.base import Base
from app.api.models.enum import SourceEnum
from app.api.models.enum import TransactionStatus


class TransactionStateEvent(Base):
    __tablename__ = "transaction_state_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "payment_transactions.id",
            ondelete="CASCADE",
            name="state_transaction_id_fk",
        ),
    )
    status: Mapped[enum.Enum] = mapped_column(
        Enum(TransactionStatus, values_callable=lambda e: [m.value for m in e])
    )
    source: Mapped[enum.Enum] = mapped_column(
        Enum(SourceEnum, values_callable=lambda e: [m.value for m in e])
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="transaction_state_events_pk"),
        Index("idx_transaction_state_events_occurred_at", occurred_at),
        Index("idx_transaction_state_events_transaction_id", transaction_id),
        Index("idx_transaction_state_events_single_row_state", transaction_id, status),
    )
