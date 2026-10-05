from __future__ import annotations

import datetime as _dt
import secrets
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base
from app.models.mixins import TimestampMixin


class Raffle(TimestampMixin, Base):
    __tablename__ = "raffles"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(nullable=True)

    starts_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    entries: Mapped[list["RaffleEntry"]] = relationship(
        "RaffleEntry",
        back_populates="raffle",
        cascade="all, delete-orphan",
    )


class RaffleEntry(TimestampMixin, Base):
    __tablename__ = "raffle_entries"

    id: Mapped[PK]

    raffle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("raffles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("parties.id", ondelete="SET NULL"),
        nullable=True,
    )

    entry_code: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        unique=True,
        default=lambda: secrets.token_urlsafe(8).upper(),
    )

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    whatsapp: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    accepts_data_processing: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    accepts_marketing: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    registered_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="whatsapp",
        server_default="whatsapp",
    )

    raffle: Mapped["Raffle"] = relationship(
        "Raffle",
        back_populates="entries",
    )

    __table_args__ = (
        UniqueConstraint(
            "raffle_id",
            "whatsapp",
            name="uq_raffle_entries_raffle_whatsapp",
        ),
        Index("ix_raffle_entries_raffle_registered_at", "raffle_id", "registered_at"),
    )

__all__ = ["Raffle", "RaffleEntry"]