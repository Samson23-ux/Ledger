import enum
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    text,
    UUID,
    DateTime,
    Enum,
    Index,
    ForeignKey,
    PrimaryKeyConstraint,
    Text,
    Boolean
)


from app.api.models.base import Base
from app.api.models.transactions import ChannelEnum


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes" \

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, server_default=text("uuid_generate_v7()")
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey(
            "wallets.id", ondelete="CASCADE", name="auth_codes_wallet_id_fk"
        ),
        unique=True
    )
    code: Mapped[str] = mapped_column(Text)
    exp_month: Mapped[str] = mapped_column(Text)
    exp_year: Mapped[str] = mapped_column(Text)
    channel: Mapped[enum.Enum] = mapped_column(
        Enum(ChannelEnum, values_callable=lambda e: [m.value for m in e]),
        default="card"
    )
    card_type: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(Text)
    reusable: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        PrimaryKeyConstraint(id, name="auth_codes_pk"),
        Index("idx_auth_codes_wallet_id", wallet_id, code, unique=True)
    )
