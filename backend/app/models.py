from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    size: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # One or more seasons, stored comma-separated (e.g. "Lente,Zomer").
    season: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    thumb_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(default=False)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[User] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Category(Base):
    """A clothing category, managed by admins in the settings panel."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class SizeOption(Base):
    """A selectable size label, managed by admins in the settings panel."""

    __tablename__ = "sizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(40), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Match(Base):
    """A verdict by one user on whether two items combine well.

    item_a_id is always the smaller id so a pair is stored canonically.
    """

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("item_a_id", "item_b_id", "user_id", name="uq_pair_user"),
        CheckConstraint("item_a_id < item_b_id", name="ck_pair_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_a_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    item_b_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 'yes' = combineert goed, 'no' = combineert niet
    verdict: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
