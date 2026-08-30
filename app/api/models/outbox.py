import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Text,
    Enum,
    PrimaryKeyConstraint,
)


from app.api.models.base import Base


class OutBoxEnum(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PROCESSING = "processing"


class OutBox(Base):
    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[enum.Enum] = mapped_column(
        Enum(OutBoxEnum, values_callable=lambda e: [m.value for m in e]),
        default=OutBoxEnum.PENDING,
    )
    locked_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (PrimaryKeyConstraint("id", name="outbox_pk"),)
