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
from app.api.models.enum import RefundStatus


class RefundStateEvent(Base):
    __tablename__ = "refund_state_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    refund_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "refunds.id",
            ondelete="CASCADE",
            name="state_refund_id_fk",
        ),
    )
    from_status: Mapped[enum.Enum | None] = mapped_column(
        Enum(RefundStatus, values_callable=lambda e: [m.value for m in e]),
        default=None,
    )
    to_status: Mapped[enum.Enum] = mapped_column(
        Enum(RefundStatus, values_callable=lambda e: [m.value for m in e])
    )
    source: Mapped[enum.Enum] = mapped_column(
        Enum(SourceEnum, values_callable=lambda e: [m.value for m in e])
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="refund_state_events_pk"),
        Index("idx_refund_state_events_refund_id", refund_id),
        Index("idx_refund_state_status", from_status, to_status),
        Index("idx_refund_state_events_occurred_at", occurred_at),
    )
