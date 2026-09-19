import uuid
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
    #: A bcrypt hash, or :data:`app.security.UNUSABLE_PASSWORD` for an account
    #: that only signs in through a federated provider. Kept NOT NULL because
    #: relaxing that in SQLite means rebuilding the table every other row in
    #: the database points at — a sentinel costs nothing and risks nothing.
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    #: "local" or "oidc" — how this account signs in, and therefore whether
    #: the app or the identity provider decides its beheerder role.
    auth_provider: Mapped[str] = mapped_column(String(20), default="local")
    #: The provider's ``sub`` claim: the *only* thing an account is recognised
    #: by on a federated login. Deliberately not the e-mail or the username,
    #: both of which a provider lets people change — and which would therefore
    #: let a renamed account walk into someone else's wardrobe.
    oidc_subject: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    #: Bumped to invalidate every token already issued for this account — what
    #: makes "log out everywhere" possible, and what makes changing a password
    #: actually end the sessions that knew the old one. Every token carries the
    #: version it was minted under; a mismatch is a dead token.
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def is_federated(self) -> bool:
        return self.oidc_subject is not None

    @property
    def has_password(self) -> bool:
        """Whether a local password can sign this account in at all."""
        return bool(self.hashed_password) and self.hashed_password.startswith("$2")


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
    # Unique per kast rather than globally: restoring someone's export into a
    # second kast has to be able to sit next to the original, and "this garment
    # in this kast" is what the uid actually identifies.
    __table_args__ = (UniqueConstraint("wardrobe_id", "uid", name="uq_item_wardrobe_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Stable identity that survives an export/import round trip. The numeric
    #: id means nothing once a backup lands in another installation, so every
    #: garment carries a UUID that travels with it: re-importing the same file
    #: updates the garment instead of duplicating it.
    uid: Mapped[str] = mapped_column(
        String(32), index=True, default=lambda: uuid.uuid4().hex
    )
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
    # Three more comma-separated tag columns in the same shape as ``season``;
    # see app/tags.py for why these are not join tables. ``occasion`` is picked
    # from an admin-managed list, ``weather`` from a fixed vocabulary the
    # forecast can actually produce, and ``style`` is free text.
    occasion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weather: Mapped[str | None] = mapped_column(String(200), nullable=True)
    style: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Indexed because serving a photo looks the garment up by filename, to
    # apply the access rules of the kast it belongs to — once per image, and a
    # wardrobe screen asks for dozens at a time.
    photo_filename: Mapped[str | None] = mapped_column(
        String(200), index=True, nullable=True
    )
    thumb_filename: Mapped[str | None] = mapped_column(
        String(200), index=True, nullable=True
    )
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


class Outfit(Base):
    """A whole outfit somebody saved: several garments under one name.

    Deliberately *not* the same thing as an approved combination. A ``Match``
    records a verdict about two garments — "these two go together" — and the
    Outfits screen assembles those into what fits with what. An ``Outfit`` is a
    decision about a specific set of clothes as a set, with the tags that say
    when to wear it: the weather, the occasion, the season. Only something that
    exists as one row can carry those, which is why recommending "wear this
    today" needed this table before anything else.
    """

    __tablename__ = "outfits"
    # Unique per kast rather than globally, for the same reason ``Item.uid`` is:
    # a backup restored beside its original must not collide with it.
    __table_args__ = (
        UniqueConstraint("wardrobe_id", "uid", name="uq_outfit_wardrobe_uid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(
        String(32), index=True, default=lambda: uuid.uuid4().hex
    )
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Comma-separated, like their namesakes on Item. See app/tags.py.
    season: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weather: Mapped[str | None] = mapped_column(String(200), nullable=True)
    style: Mapped[str | None] = mapped_column(String(200), nullable=True)

    wardrobe_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[User] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    entries: Mapped[list["OutfitItem"]] = relationship(
        back_populates="outfit",
        cascade="all, delete-orphan",
        order_by="OutfitItem.position",
    )
    wears: Mapped[list["WearLog"]] = relationship(
        back_populates="outfit", cascade="all, delete-orphan"
    )

    @property
    def items(self) -> list["Item"]:
        """The garments themselves, in the order they were put together."""
        return [entry.item for entry in self.entries if entry.item is not None]


class OutfitItem(Base):
    """One garment's place in one outfit."""

    __tablename__ = "outfit_items"
    __table_args__ = (
        UniqueConstraint("outfit_id", "item_id", name="uq_outfit_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    outfit: Mapped[Outfit] = relationship(back_populates="entries")
    item: Mapped[Item] = relationship(lazy="joined")


class WearLog(Base):
    """"I wore this outfit on this day", by one person.

    Per user, not per wardrobe: two people sharing a kast wear different
    things, and only your own history should decide what the app suggests to
    you. Whether it is kept at all is each user's own choice — see
    ``UserPreference.wear_log_enabled``.
    """

    __tablename__ = "wear_logs"
    __table_args__ = (
        UniqueConstraint("outfit_id", "user_id", "worn_on", name="uq_wear_once_a_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: The day itself, as "JJJJ-MM-DD". A plain date: which calendar day
    #: something was worn on is the whole point, and a timestamp would drag a
    #: timezone into a question that does not have one.
    worn_on: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    outfit: Mapped[Outfit] = relationship(back_populates="wears")


class DayPlan(Base):
    """"On this day I am wearing that outfit" — one square of the week planner.

    Per user as well as per wardrobe: a planner is a personal diary of what you
    intend to wear, and two people sharing a kast plan their own weeks.
    """

    __tablename__ = "day_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_day_plan_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    wardrobe_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True
    )
    #: "JJJJ-MM-DD", like ``WearLog.worn_on`` and for the same reason.
    day: Mapped[str] = mapped_column(String(10), index=True)
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    outfit: Mapped[Outfit] = relationship(lazy="joined")


class Trip(Base):
    """A journey to pack for: some days, some outfits, and a packing list."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Both "JJJJ-MM-DD", both optional: a weekend away that is not planned to
    #: the day is still worth a packing list.
    starts_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ends_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    wardrobe_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    outfits: Mapped[list["TripOutfit"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    packed: Mapped[list["TripPacked"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class TripOutfit(Base):
    """An outfit taken along on a trip."""

    __tablename__ = "trip_outfits"
    __table_args__ = (UniqueConstraint("trip_id", "outfit_id", name="uq_trip_outfit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), index=True
    )

    trip: Mapped[Trip] = relationship(back_populates="outfits")
    outfit: Mapped[Outfit] = relationship(lazy="joined")


class TripPacked(Base):
    """A garment ticked off a trip's packing list.

    The list itself is *derived* — every garment in every outfit taken along —
    so it cannot go stale when an outfit changes. Only the ticks are stored,
    and a tick for a garment no longer on the list simply never shows up.
    """

    __tablename__ = "trip_packed"
    __table_args__ = (UniqueConstraint("trip_id", "item_id", name="uq_trip_packed"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )

    trip: Mapped[Trip] = relationship(back_populates="packed")


class StyleProfile(Base):
    """Someone's "stijl-DNA": the colours and words they dress by.

    Per user, and read by the recommendation engine: an outfit in your own
    palette, in the style words you picked, is scored above one that merely
    matches the weather. It is a preference, never a filter — a kast you share
    with someone whose taste differs must keep working for both of you.
    """

    __tablename__ = "style_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Comma-separated base colour names (see app/suggestions.BASE_COLORS).
    colors: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Comma-separated style words, the same vocabulary garments carry.
    styles: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Occasions this person dresses for most, used to order suggestions.
    occasions: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class OccasionOption(Base):
    """An occasion ("Werk", "Uit eten"), managed by admins like categories."""

    __tablename__ = "occasions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class UserPreference(Base):
    """Per-user choices that are nobody else's business.

    One row per account, created on first read. Everything here is personal
    rather than per wardrobe on purpose: two people sharing a kast can want a
    different colour scheme, a different location for the forecast, and one of
    them may not want a wear log at all.
    """

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Key of a palette in the frontend's theme list. Free text rather than an
    #: enum: adding a palette is a frontend change, and a server that rejects
    #: an unknown name would make that a two-sided release.
    theme: Mapped[str] = mapped_column(String(40), default="midnight")
    #: Whether this user keeps a wear log at all. Off by default — it is a
    #: feature you opt into, not a thing the app starts recording about you.
    wear_log_enabled: Mapped[bool] = mapped_column(default=False)
    #: Where to fetch the forecast. Set either by the browser's location
    #: permission or by searching for a place; blank means "never asked".
    location_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    #: "auto" fetches the forecast, "manual" uses ``manual_weather`` — for
    #: somebody who would rather not share a location, or a server with no way
    #: out to the internet.
    weather_mode: Mapped[str] = mapped_column(String(10), default="auto")
    #: Comma-separated weather tags, used when ``weather_mode`` is "manual".
    manual_weather: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Hoe deze persoon temperatuur beleeft, als verschuiving in graden op de
    #: banden van :mod:`app.weather`. Positief = eerder warm dan de thermometer
    #: zegt. 0 is de standaard en betekent "zoals het weerbericht het zegt".
    temperature_preference: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


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
    # The kast the link gives access to, or NULL for an account invitation: one
    # handed out by a beheerder that only creates an account (with its own
    # kast) and shares nothing.
    wardrobe_id: Mapped[int | None] = mapped_column(
        ForeignKey("wardrobes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    wardrobe: Mapped["Wardrobe | None"] = relationship()
    # ROLE_EDITOR | ROLE_VIEWER — the role the invitee gets on acceptance.
    # Meaningless (and ignored) for an account invitation.
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
    def kind(self) -> str:
        """"account" (a new login) | "wardrobe" (access to an existing kast)."""
        return "wardrobe" if self.wardrobe_id is not None else "account"

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


class AppSetting(Base):
    """One admin-tunable setting, stored as text under a stable key.

    A table rather than an environment variable because these are toggled from
    inside the app: a beheerder flipping self-registration should not have to
    edit a compose file and restart the container. Values are strings so a new
    setting never needs a migration; :mod:`app.app_settings` does the parsing.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


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
