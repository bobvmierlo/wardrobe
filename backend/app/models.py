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


# Roles a member can hold on someone else's wardrobe.
ROLE_EDITOR = "editor"  # may add, edit and delete garments (and vote)
ROLE_VIEWER = "viewer"  # may only look and vote on combinations


class Wardrobe(Base):
    """A user's personal wardrobe ("kast").

    Every user owns exactly one wardrobe, created automatically. Other users
    can be invited to it as an editor or a viewer via ``WardrobeMember``.
    """

    __tablename__ = "wardrobes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    owner: Mapped[User] = relationship()
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WardrobeMember(Base):
    """An invitation granting a user access to another user's wardrobe."""

    __tablename__ = "wardrobe_members"
    __table_args__ = (
        UniqueConstraint("wardrobe_id", "user_id", name="uq_wardrobe_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wardrobe_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    user: Mapped[User] = relationship()
    # ROLE_EDITOR | ROLE_VIEWER
    role: Mapped[str] = mapped_column(String(10), default=ROLE_VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Brand(Base):
    """A clothing brand, shared across every wardrobe in the installation.

    Brands live in their own table so the same brand can only exist once: the
    name is unique and compared case-insensitively (NOCASE), so "Nike", "NIKE"
    and "nike" all resolve to one row. Unlike categories and sizes this is not
    an admin-managed list — any user adds a brand simply by naming it on a
    garment.
    """

    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(120, collation="NOCASE"), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), index=True)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id"), index=True, nullable=True
    )
    brand_ref: Mapped["Brand | None"] = relationship(lazy="joined")
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    size: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # One or more seasons, stored comma-separated (e.g. "Lente,Zomer").
    season: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    thumb_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(default=False)

    # The wardrobe this garment lives in. Nullable only so an in-place SQLite
    # migration can add the column and backfill it on existing installs.
    wardrobe_id: Mapped[int | None] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[User] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def brand(self) -> str | None:
        """The brand name, so the API keeps exposing a plain string."""
        return self.brand_ref.name if self.brand_ref else None


class Category(Base):
    """A clothing category, managed by admins in the settings panel."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class SizeOption(Base):
    """A selectable size label, managed by admins in the settings panel.

    ``kind`` groups sizes so the form can offer the right ones per category:
    "clothing" (XS-XXXL), "shoes" (EU numbers) or "accessory" (One-size).
    """

    __tablename__ = "sizes"
    # Unique per kind, not globally: a clothing size "40" (EU pants) and a shoe
    # size "40" are different labels that must be able to coexist.
    __table_args__ = (UniqueConstraint("label", "kind", name="uq_sizes_label_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20), default="clothing")
    position: Mapped[int] = mapped_column(Integer, default=0)


class ColorRule(Base):
    """An admin-editable colour-combination rule used by the suggestion engine.

    Colours are stored as normalised base names (e.g. "navy", "beige") in a
    canonical order (color_a <= color_b) so each unordered pair is unique.
    ``verdict`` is "good" (looks nice) or "bad" (clashes).
    """

    __tablename__ = "color_rules"
    __table_args__ = (
        UniqueConstraint("color_a", "color_b", "verdict", name="uq_color_rule"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    color_a: Mapped[str] = mapped_column(String(20))
    color_b: Mapped[str] = mapped_column(String(20))
    verdict: Mapped[str] = mapped_column(String(8))  # "good" | "bad"


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


class MatchSkip(Base):
    """A pair the user postponed instead of judging ("sla over").

    Skipping is deliberately *not* a verdict: the pair stays unjudged, it just
    moves to the back of the queue so the swipe screen offers everything else
    first. Stored canonically (item_a_id < item_b_id) like ``Match``; giving a
    verdict later removes the skip again.
    """

    __tablename__ = "match_skips"
    __table_args__ = (
        UniqueConstraint("item_a_id", "item_b_id", "user_id", name="uq_skip_pair_user"),
        CheckConstraint("item_a_id < item_b_id", name="ck_skip_pair_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_a_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    item_b_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invitation(Base):
    """A shareable link that grants access to one wardrobe.

    Unlike ``WardrobeMember`` — which needs the invitee to already have an
    account — an invitation is created *before* knowing who will use it. The
    holder of the link either signs in and accepts, or (since open registration
    is disabled) registers a brand-new account through this very link.

    The row is kept after use so the audit trail can show who accepted what.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # URL-safe random secret; the only thing that proves you were invited.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wardrobe_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True
    )
    wardrobe: Mapped["Wardrobe"] = relationship()
    # ROLE_EDITOR | ROLE_VIEWER — the role the invitee gets on acceptance.
    role: Mapped[str] = mapped_column(String(10), default=ROLE_VIEWER)
    # Free-text reminder of who this link was meant for (name or e-mail).
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_by: Mapped["User | None"] = relationship(foreign_keys=[accepted_by_id])
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def status(self) -> str:
        """"revoked" | "accepted" | "expired" | "open" — never two at once."""
        if self.revoked_at is not None:
            return "revoked"
        if self.accepted_at is not None:
            return "accepted"
        if self.expires_at is not None and as_utc(self.expires_at) < utcnow():
            return "expired"
        return "open"


class AuditLog(Base):
    """Who did what, when — the trail an admin reads back in the app.

    ``user_name`` duplicates the actor's display name on purpose: entries must
    stay readable after the account is deleted, so the row never depends on the
    user still existing. ``detail`` holds a short human-readable sentence in
    Dutch rather than a machine format, because that is what the log screen
    shows.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # e.g. "match.verdict", "item.create" — "<onderwerp>.<handeling>".
    action: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_name: Mapped[str] = mapped_column(String(100), default="onbekend")
    wardrobe_id: Mapped[int | None] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat those as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
