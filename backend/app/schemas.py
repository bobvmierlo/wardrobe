from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


# ---- Users / auth ----
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    is_admin: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4, max_length=128)
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_admin: bool


class PasswordChange(BaseModel):
    new_password: str = Field(min_length=4, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Items ----
class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    season: str | None = None
    notes: str | None = None
    is_favorite: bool = False


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    photo_filename: str | None
    thumb_filename: str | None
    wardrobe_id: int | None
    created_by_id: int
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def seasons(self) -> list[str]:
        """Season stored comma-separated, surfaced as a clean list."""
        if not self.season:
            return []
        return [s.strip() for s in self.season.split(",") if s.strip()]


# ---- Wardrobes (kasten) & sharing ----
class WardrobeOut(BaseModel):
    """A wardrobe the current user can reach, with their role on it."""
    id: int
    name: str
    owner: UserOut
    # "owner" | "admin" | "editor" | "viewer" — the current user's role.
    my_role: str
    can_edit: bool
    can_manage: bool
    member_count: int


class WardrobeMemberOut(BaseModel):
    user: UserOut
    role: str  # "editor" | "viewer"


class MemberInvite(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    role: str = Field(pattern="^(editor|viewer)$")


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern="^(editor|viewer)$")


# ---- Categories & sizes (admin-managed lists) ----
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class SizeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    kind: str


class LabelIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    kind: str = Field(default="clothing", pattern="^(clothing|shoes|accessory)$")


# ---- Webshop import ----
class ScrapeResult(BaseModel):
    name: str | None = None
    brand: str | None = None
    color: str | None = None
    price: str | None = None
    description: str | None = None
    images: list[str] = []


# ---- Outfit suggestions ----
class OutfitSuggestion(BaseModel):
    items: list[ItemOut]
    score: int
    reason: str
    # False for everything the API returns — suggestions that are already a
    # combination are filtered out — but sent explicitly so the frontend can
    # disable "accepteren" instead of guessing.
    already_combined: bool = False


class SuggestionAccept(BaseModel):
    """Accept a suggested outfit as a real combination."""
    item_ids: list[int] = Field(min_length=2, max_length=6)


# ---- Colour-combination rules (editable suggestion logic) ----
class ColorRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    color_a: str
    color_b: str
    verdict: str


class ColorRuleIn(BaseModel):
    color_a: str = Field(min_length=1, max_length=20)
    color_b: str = Field(min_length=1, max_length=20)
    verdict: str = Field(pattern="^(good|bad)$")


class ColorLogic(BaseModel):
    """Everything the settings screen needs to explain and edit the logic."""
    rules: list[ColorRuleOut]
    neutrals: list[str]
    colors: list[str]


# ---- Matches ----
class MatchCreate(BaseModel):
    item_a_id: int
    item_b_id: int
    verdict: str = Field(pattern="^(yes|no)$")


class PairOut(BaseModel):
    """A pair of items presented for judging in the swipe screen."""
    anchor: ItemOut
    candidate: ItemOut
    # True when this pair was skipped earlier and has come back around.
    skipped: bool = False


class PairSkip(BaseModel):
    """Postpone a pair: no verdict, just move it to the back of the queue."""
    item_a_id: int
    item_b_id: int


class PairVote(BaseModel):
    """One member's verdict on a pair, for the "already judged" overview."""
    user_id: int
    display_name: str
    verdict: str  # "yes" | "no"


class JudgedPair(BaseModel):
    """A pair the current user already judged, so they can undo or flip it."""
    item_a: ItemOut
    item_b: ItemOut
    my_verdict: str  # "yes" | "no"
    votes: list[PairVote]
    updated_at: datetime


class OutfitPartner(BaseModel):
    item: ItemOut
    approved_by: list[str]  # display names who said 'yes'


class RejectedPartner(BaseModel):
    """A garment that was judged *not* to go with this one.

    Both sides are reported, because the interesting case is a split vote: you
    said yes, your partner said no, and the combination is blocked. Without
    seeing the "nee" that would be inexplicable.
    """
    item: ItemOut
    rejected_by: list[str]  # display names who said 'no'
    approved_by: list[str]  # display names who said 'yes' anyway
    # Whether the current user is one of the people who said no. Only their own
    # verdict is theirs to withdraw, so this decides if undo is offered at all.
    rejected_by_me: bool


# ---- Invitation links ----
class InvitationCreate(BaseModel):
    role: str = Field(default="viewer", pattern="^(editor|viewer)$")
    # Free-text reminder of who the link is for (a name or e-mail address).
    label: str | None = Field(default=None, max_length=120)
    # How long the link stays usable. None = no expiry.
    expires_days: int | None = Field(default=14, ge=1, le=365)


class InvitationOut(BaseModel):
    """An invitation link as its creator sees it, token included."""
    id: int
    token: str
    # Path to open in a browser, e.g. "/invite/abc123". The frontend turns it
    # into a full URL with its own origin, so the backend needs no base-URL
    # setting that could go stale behind a reverse proxy.
    path: str
    role: str
    label: str | None
    status: str  # "open" | "accepted" | "expired" | "revoked"
    created_at: datetime
    expires_at: datetime | None
    accepted_at: datetime | None
    accepted_by: UserOut | None


class InvitationInfo(BaseModel):
    """What the (not yet logged-in) holder of a link is told about it.

    Deliberately thin: the wardrobe's name and owner, nothing about its
    contents or its other members.
    """
    wardrobe_name: str
    owner_name: str
    role: str
    label: str | None
    status: str
    expires_at: datetime | None


class InvitationRegister(BaseModel):
    """Sign up through an invitation link — the only way to get an account."""
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4, max_length=128)


# ---- Logging & audit trail (admin) ----
class AuditEntryOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    action_label: str
    user_id: int | None
    user_name: str
    wardrobe_id: int | None
    wardrobe_name: str | None
    entity_type: str | None
    entity_id: int | None
    detail: str


class AuditPage(BaseModel):
    entries: list[AuditEntryOut]
    total: int
    # Every action present in the log, so the filter dropdown only offers
    # values that actually occur.
    actions: list[str]


class LogEntryOut(BaseModel):
    id: int
    time: datetime
    level: str
    logger: str
    message: str
