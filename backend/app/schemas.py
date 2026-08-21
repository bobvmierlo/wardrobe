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
    created_by_id: int
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def seasons(self) -> list[str]:
        """Season stored comma-separated, surfaced as a clean list."""
        if not self.season:
            return []
        return [s.strip() for s in self.season.split(",") if s.strip()]


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
