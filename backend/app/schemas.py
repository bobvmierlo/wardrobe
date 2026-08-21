from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
