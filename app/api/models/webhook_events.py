import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Index,
    Text,
    Boolean,
    BigInteger,
    PrimaryKeyConstraint,
)


from app.api.models.base import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    paystack_data_id: Mapped[int | None] = mapped_column(BigInteger)
    paystack_reference: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    signature_verified: Mapped[bool] = mapped_column(Boolean)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="webhook_events_pk"),
        Index(
            "idx_webhook_events_dedup_comp",
            paystack_data_id,
            paystack_reference,
            event_type,
            unique=True,
        ),
    )
