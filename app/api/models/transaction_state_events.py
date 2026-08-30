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
    entity_type: Mapped[enum.Enum] = mapped_column(
        Enum(EntityEnum, values_callable=lambda e: [m.value for m in e])
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
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
        Index("idx_transaction_state_events_entity", entity_type, entity_id),
        Index("idx_transaction_state_events_occurred_at", occurred_at),
    )
