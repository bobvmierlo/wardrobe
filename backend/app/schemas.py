from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .config import settings
from .tags import split_tags

#: Read once, at import, so every password field in the API agrees. Raising it
#: never locks anyone out: it applies when a password is *set*, not when one is
#: checked, so existing logins keep working and only meet it next time.
MIN_PASSWORD = settings.min_password_length


# ---- Users / auth ----
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    is_admin: bool
    #: "local" or "oidc" — shown on the accounts screen so a beheerder can see
    #: at a glance which roles are theirs to change and which the provider owns.
    auth_provider: str = "local"


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=MIN_PASSWORD, max_length=128)
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_admin: bool


class PasswordChange(BaseModel):
    """Changing your own password.

    ``current_password`` is optional in the schema but required in practice for
    any account that has one — the route checks that, because only the route
    knows whether this account signs in with a password at all. An account that
    only uses SSO is setting a first one and has nothing to prove.
    """
    current_password: str | None = None
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegistrationIn(BaseModel):
    """The details a newcomer picks for themselves when creating an account.

    Used both for self-registration (when a beheerder has opened it) and for
    registering through an invitation link.
    """
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=MIN_PASSWORD, max_length=128)


class AuthConfig(BaseModel):
    """What the login screen needs to know before anyone has signed in.

    Public on purpose, and deliberately thin: whether the front door is open,
    and whether there is an SSO button to draw. Nothing about *which* provider
    beyond the label the operator chose — an unauthenticated caller has no
    business learning the issuer URL.
    """
    self_registration: bool
    #: True when federated login is configured well enough to try.
    oidc_enabled: bool = False
    #: The text for the SSO button.
    oidc_label: str = ""
    #: True when a group mapping is configured, so the provider owns the
    #: beheerder role and the accounts screen must not offer to change it.
    oidc_manages_admins: bool = False
    #: Whether to show the username/password form without being asked. The
    #: form is always *reachable*; see ``WARDROBE_LOCAL_LOGIN``.
    local_login: bool = True
    #: Shortest password this installation accepts, so the forms can say so
    #: before the server has to refuse anything.
    min_password_length: int = MIN_PASSWORD


class AuthConfigUpdate(BaseModel):
    """The one thing a beheerder may change here.

    Separate from :class:`AuthConfig` because the rest of that model is set by
    the operator in the environment, and a PUT must not look like it could
    change it.
    """
    self_registration: bool


class OidcExchange(BaseModel):
    """The one-time code the app trades for a token after an SSO redirect."""
    code: str = Field(min_length=8, max_length=200)


# ---- Items ----
class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    season: str | None = None
    # Comma-separated, like ``season``; surfaced as lists below. See app/tags.py.
    occasion: str | None = None
    weather: str | None = None
    style: str | None = None
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
        return split_tags(self.season)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def occasions(self) -> list[str]:
        return split_tags(self.occasion)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def weather_tags(self) -> list[str]:
        return split_tags(self.weather)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def style_tags(self) -> list[str]:
        return split_tags(self.style)


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
    """A pair of items presented for judging in the swipe screen.

    Always the same way round: ``anchor`` is the bovenstuk (shown on the left)
    and ``candidate`` the onderstuk (the card being swiped, on the right), no
    matter which of the two the queue was anchored on. Comparing is easier when
    the sides never move, and it means the same two garments cannot show up a
    second time with the sides swapped.
    """
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


class AccountInvitationCreate(BaseModel):
    """A beheerder's link to a brand-new account, without sharing any kast."""
    label: str | None = Field(default=None, max_length=120)
    expires_days: int | None = Field(default=14, ge=1, le=365)


class InvitationOut(BaseModel):
    """An invitation link as its creator sees it, token included."""
    id: int
    token: str
    # "wardrobe" (access to an existing kast) | "account" (a new login only).
    kind: str
    wardrobe_name: str | None
    # Path to open in a browser, e.g. "/invite/abc123". The frontend turns it
    # into a full URL with its own origin, so the backend needs no base-URL
    # setting that could go stale behind a reverse proxy.
    path: str
    # The role the link grants on the kast — None for an account invitation,
    # which shares no kast to have a role on.
    role: str | None
    label: str | None
    status: str  # "open" | "accepted" | "expired" | "revoked"
    created_at: datetime
    expires_at: datetime | None
    accepted_at: datetime | None
    accepted_by: UserOut | None


class InvitationInfo(BaseModel):
    """What the (not yet logged-in) holder of a link is told about it.

    Deliberately thin: the wardrobe's name and owner, nothing about its
    contents or its other members. An account invitation shares no kast at
    all, so it leaves those empty.
    """
    kind: str  # "wardrobe" | "account"
    wardrobe_name: str | None = None
    owner_name: str | None = None
    role: str | None = None
    label: str | None
    status: str
    expires_at: datetime | None


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


# ---- Automatic backups ----
class ScheduledBackupOut(BaseModel):
    """One backup file sitting in <data>/backups.

    The size in bytes rather than a rounded megabyte: a fresh installation's
    backup is a few kilobytes, and "0.0 MB" reads as "nothing was saved".
    Choosing the unit is the screen's job.
    """
    name: str
    size_bytes: int
    created_at: datetime


class ScheduledBackupsOut(BaseModel):
    """The schedule, and what it has produced."""
    #: "UU:MM", or empty when no schedule is set.
    time: str
    keep: int
    #: False when unset *or* unparseable — the log says which.
    enabled: bool
    backups: list[ScheduledBackupOut]


# ---- Occasions (admin-managed list, like categories) ----
class OccasionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


# ---- Outfits (saved sets of garments) ----
class OutfitIn(BaseModel):
    """What the app sends when saving an outfit.

    Tags arrive as lists and are stored comma-separated; the API never asks a
    client to know about that (see app/tags.py).
    """
    name: str = Field(min_length=1, max_length=120)
    item_ids: list[int] = Field(min_length=1, max_length=12)
    notes: str | None = Field(default=None, max_length=2000)
    seasons: list[str] = []
    occasions: list[str] = []
    weather_tags: list[str] = []
    style_tags: list[str] = []


class OutfitOut(BaseModel):
    id: int
    name: str
    notes: str | None
    items: list[ItemOut]
    seasons: list[str]
    occasions: list[str]
    weather_tags: list[str]
    style_tags: list[str]
    created_by_id: int
    created_at: datetime
    #: How often the *current user* logged wearing this, and when they last
    #: did. Empty for anyone who keeps no wear log — theirs is the only history
    #: that is ever counted here.
    wear_count: int = 0
    last_worn: str | None = None


class WearIn(BaseModel):
    """Log (or unlog) a day this outfit was worn. Defaults to today."""
    worn_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class WearOut(BaseModel):
    outfit_id: int
    worn_on: str


# ---- Recommendations ("je zou dit aan kunnen trekken") ----
class RecommendationOut(BaseModel):
    items: list[ItemOut]
    score: int
    reason: str
    # "saved" = an outfit you put together before, "new" = assembled just now.
    source: str
    outfit_id: int | None = None
    outfit_name: str | None = None
    last_worn: str | None = None


class RecommendationPage(BaseModel):
    """Everything the "Vandaag" screen paints in one request."""
    weather: "WeatherOut | None" = None
    advice: str = ""
    occasion: str | None = None
    recommendations: list[RecommendationOut] = []
    #: Why there is nothing to show, when there is nothing to show.
    empty_reason: str | None = None


# ---- Weather ----
class PlaceOut(BaseModel):
    name: str
    label: str
    latitude: float
    longitude: float
    region: str | None = None
    country: str | None = None
    postcode: str | None = None


class WeatherOut(BaseModel):
    location: str
    description: str
    temperature: float
    apparent_temperature: float
    wind_speed: float
    precipitation: float
    precipitation_chance: int | None = None
    high: float | None = None
    low: float | None = None
    is_day: bool = True
    tags: list[str] = []
    #: "auto" (fetched) or "manual" (the tags this user picked themselves).
    mode: str = "auto"


# ---- Per-user preferences ----
class TemperatureOption(BaseModel):
    """Eén stap op de schaal "heb ik het snel koud of snel warm"."""
    #: Verschuiving in graden op de temperatuurbanden. Positief = eerder warm.
    value: int
    label: str
    hint: str


class PreferencesOut(BaseModel):
    theme: str
    wear_log_enabled: bool
    location_label: str | None
    latitude: float | None
    longitude: float | None
    weather_mode: str
    manual_weather: list[str]
    #: False when the operator switched the weather off for this installation,
    #: so the screens can say so instead of showing a button that cannot work.
    weather_available: bool = True
    #: Hoe deze persoon temperatuur beleeft, in graden verschuiving.
    temperature_preference: int = 0
    #: De hele schaal, zodat het instellingenscherm geen tweede verzoek hoeft.
    temperature_options: list[TemperatureOption] = []


class PreferencesIn(BaseModel):
    theme: str | None = Field(default=None, max_length=40)
    wear_log_enabled: bool | None = None
    location_label: str | None = Field(default=None, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    weather_mode: str | None = Field(default=None, pattern="^(auto|manual)$")
    manual_weather: list[str] | None = None
    #: Begrensd op de schaal zelf; de route klemt wat er binnenkomt nog eens.
    temperature_preference: int | None = Field(default=None, ge=-10, le=10)


# ---- Week planner ----
class DayPlanOut(BaseModel):
    day: str
    outfit: OutfitOut | None = None
    #: The forecast for that day, when it is close enough to have one.
    weather: WeatherOut | None = None


class WeekOut(BaseModel):
    start: str
    days: list[DayPlanOut]


class PlanIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    #: None clears the day.
    outfit_id: int | None = None


# ---- Trips (reistas) ----
class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    starts_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    ends_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = Field(default=None, max_length=2000)


class PackingEntry(BaseModel):
    item: ItemOut
    packed: bool
    #: How many of the trip's outfits need this garment — the thing that makes
    #: a packing list shorter than the sum of its outfits.
    used_in: int


class TripOut(BaseModel):
    id: int
    name: str
    destination: str | None
    starts_on: str | None
    ends_on: str | None
    notes: str | None
    outfit_count: int
    item_count: int
    packed_count: int


class TripDetail(TripOut):
    outfits: list[OutfitOut]
    packing: list[PackingEntry]


class TripOutfitIn(BaseModel):
    outfit_id: int


class PackedIn(BaseModel):
    item_id: int
    packed: bool


# ---- Style DNA & style guide ----
class StyleProfileOut(BaseModel):
    colors: list[str]
    styles: list[str]
    occasions: list[str]
    notes: str | None = None
    #: The vocabularies the form offers, so the screen needs no second request.
    available_colors: list[str] = []
    available_styles: list[str] = []
    available_occasions: list[str] = []


class StyleProfileIn(BaseModel):
    colors: list[str] | None = None
    styles: list[str] | None = None
    occasions: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class GuideColor(BaseModel):
    """One colour in the wardrobe, and what the rules say it goes with."""
    color: str
    count: int
    goes_with: list[str]
    clashes_with: list[str]
    in_profile: bool = False


class GuideGap(BaseModel):
    """Something the wardrobe is thin on, phrased as advice."""
    title: str
    detail: str


class StyleGuideOut(BaseModel):
    colors: list[GuideColor]
    neutrals: list[str]
    gaps: list[GuideGap]
    #: Weather this wardrobe has little or nothing tagged for.
    uncovered_weather: list[str]
    tips: list[str]


# ---- Insights (inzichten) ----
class CountEntry(BaseModel):
    label: str
    count: int


class ColorSlice(BaseModel):
    color: str
    count: int


class InsightsOut(BaseModel):
    item_count: int
    outfit_count: int
    favorite_count: int
    #: Garments that are in no saved outfit at all.
    unused_items: list[ItemOut]
    by_category: list[CountEntry]
    by_season: list[CountEntry]
    by_occasion: list[CountEntry]
    palette: list[ColorSlice]
    #: Only filled for a user who keeps a wear log.
    wear_log_enabled: bool = False
    total_wears: int = 0
    most_worn: list[OutfitOut] = []
    #: Garments not worn in a long time (or never), for "Opruimen".
    neglected: list[ItemOut] = []


RecommendationPage.model_rebuild()


# ---- Aanvullen: tags raden en looks samenstellen voor een bestaande kast ----
class AutofillPreview(BaseModel):
    """What the two buttons would do, before either is pressed."""
    item_count: int
    #: Garments with nothing filled in for that field yet.
    without_weather: int
    without_occasion: int
    #: How many of those this would actually be able to fill in — the rest are
    #: garments where the category says nothing useful.
    taggable: int
    outfit_count: int
    #: How many new looks could be built right now, up to what was asked for.
    composable: int
    #: Whether this installation has the optional AI layer configured. False
    #: means the screen must not offer it — see app/ai.py.
    ai_available: bool = False


class TaggedItem(BaseModel):
    """One garment and what was (or would be) written onto it."""
    id: int
    name: str
    category: str
    weather: list[str] = []
    occasions: list[str] = []


class AutofillTagsResult(BaseModel):
    tagged: int
    #: How many of those came from the AI layer rather than the rules. Always
    #: reported, so nobody has to guess where a label came from.
    by_ai: int = 0
    #: Set when the AI was asked for but could not be reached; the rules ran
    #: anyway, and this says so instead of failing the whole action.
    ai_note: str | None = None
    #: The first handful, so the screen can show what it did rather than only
    #: a number. Everything is editable on the garment's own page afterwards.
    examples: list[TaggedItem] = []


class ComposedLook(BaseModel):
    name: str
    items: list[ItemOut]
    seasons: list[str] = []
    occasions: list[str] = []
    weather_tags: list[str] = []
    style_tags: list[str] = []
    reason: str = ""


class AutofillLooksResult(BaseModel):
    created: list[OutfitOut] = []
    #: How many of these the AI layer composed. The rest the app built itself,
    #: which is also what happens when the AI returns too few or none.
    by_ai: int = 0
    #: Says what the AI layer did or could not do — including how many of its
    #: proposals were thrown out, and why.
    ai_note: str | None = None
    #: Filled instead of ``created`` when nothing was saved (a dry run).
    proposed: list[ComposedLook] = []
    #: Why fewer came back than were asked for, when that happened.
    note: str | None = None



# ---- De AI-laag, zoals een beheerder 'm in de app instelt ----
class AiModelOption(BaseModel):
    value: str
    label: str


class AiSettingsOut(BaseModel):
    """Wat er staat. Met opzet zónder de sleutel zelf."""
    enabled: bool
    model: str
    effort: str
    #: Of er een sleutel staat, en de laatste vier tekens ervan. De sleutel
    #: zelf verlaat de server niet — ook niet naar een beheerder.
    key_set: bool
    key_hint: str | None = None
    #: Velden die in de omgeving van de server vastliggen en hier dus niet te
    #: wijzigen zijn.
    locked: list[str] = []
    models: list[AiModelOption] = []
    efforts: list[str] = []
    timeout_seconds: float = 60.0


class AiSettingsIn(BaseModel):
    enabled: bool | None = None
    model: str | None = Field(default=None, max_length=80)
    effort: str | None = Field(default=None, max_length=20)
    #: Een lege string wist de sleutel; weglaten laat 'm staan.
    api_key: str | None = Field(default=None, max_length=200)
