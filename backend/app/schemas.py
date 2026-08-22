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


class OutfitPartner(BaseModel):
    item: ItemOut
    approved_by: list[str]  # display names who said 'yes'
