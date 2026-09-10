import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Text,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    Index,
)

from app.api.models.base import Base
from app.api.models.state import TransactionStatus


class EntityEnum(str, enum.Enum):
    REFUND = "refund"
    PAYMENT_TRANSACTION = "payment_transaction"


class SourceEnum(str, enum.Enum):
    WEBHOOK = "webhook"
    USER_ACTION = "user_action"
    RECONCILIATION = "reconciliation"


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
    entity_type: Mapped[enum.Enum] = mapped_column(
        Enum(EntityEnum, values_callable=lambda e: [m.value for m in e])
    )
    from_status: Mapped[enum.Enum | None] = mapped_column(
        Enum(TransactionStatus, values_callable=lambda e: [m.value for m in e]),
        default=None,
    )
    to_status: Mapped[enum.Enum] = mapped_column(
        Enum(TransactionStatus, values_callable=lambda e: [m.value for m in e])
    )
    source: Mapped[enum.Enum] = mapped_column(
        Enum(SourceEnum, values_callable=lambda e: [m.value for m in e])
    )
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("webhook_events.id")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="transaction_state_events_pk"),
        Index("idx_transaction_state_events_entity", transaction_id, entity_type),
        Index("idx_transaction_state_status", from_status, to_status),
        Index("idx_transaction_state_events_occurred_at", occurred_at),
    )
