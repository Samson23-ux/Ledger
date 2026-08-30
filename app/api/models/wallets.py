import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Enum,
    Index,
    ForeignKey,
    PrimaryKeyConstraint,
)


from app.api.models.base import Base


class CurrencyEnum(str, enum.Enum):
    NGN = "NGN"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE", name="wallets_user_id_fk"),
        unique=True,
    )
    balance: Mapped[int] = mapped_column(BIGINT)
    currency: Mapped[enum.Enum] = mapped_column(
        Enum(CurrencyEnum, values_callable=lambda e: [m.value for m in e]),
        default=CurrencyEnum.NGN,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="wallets_pk"),
        Index("idx_wallets_user_id", id, user_id, unique=True),
    )
