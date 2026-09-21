"""Everything that belongs to one person rather than to a kast.

Their colour scheme, where the forecast comes from, whether a wear log is kept
at all, their stijl-DNA — and the style guide, which is what the app makes of
their wardrobe once it knows those things.
"""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..access import require_view
from .. import weather as weather_service
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, OccasionOption, User
from ..preferences import get_preferences, get_profile, serialize
from ..routers.color_rules import load_pairs
from ..schemas import (
    GuideColor,
    GuideGap,
    PreferencesIn,
    PreferencesOut,
    StyleGuideOut,
    StyleProfileIn,
    StyleProfileOut,
)
from ..suggestions import BASE_COLORS, NEUTRALS, normalize_color
from ..tags import DEFAULT_STYLES, WEATHER_TAGS, join_tags, split_tags

router = APIRouter(prefix="/api/me", tags=["me"])


def _partners(pairs: set[frozenset[str]], color: str) -> set[str]:
    """The other colour of every rule this one takes part in.

    Rules are stored as unordered pairs, and a rule about a colour and itself
    ("ton-sur-ton") has only one member — hence the length check rather than
    assuming there is always something on the other side.
    """
    return {
        next(iter(pair - {color}))
        for pair in pairs
        if color in pair and len(pair) == 2
    }


@router.get("/preferences", response_model=PreferencesOut)
def read_preferences(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return serialize(get_preferences(db, user))


@router.put("/preferences", response_model=PreferencesOut)
def write_preferences(
    body: PreferencesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change some of your own settings. Anything left out stays as it was."""
    prefs = get_preferences(db, user)
    if body.theme is not None:
        prefs.theme = body.theme.strip() or "midnight"
    if body.wear_log_enabled is not None:
        prefs.wear_log_enabled = body.wear_log_enabled
    if body.temperature_preference is not None:
        prefs.temperature_preference = weather_service.clamp_offset(
            body.temperature_preference
        )
    if body.weather_mode is not None:
        prefs.weather_mode = body.weather_mode
    if body.manual_weather is not None:
        prefs.manual_weather = join_tags(
            [t for t in body.manual_weather if t in WEATHER_TAGS]
        )
    # The three location fields move together: a label without coordinates
    # would name a place the forecast cannot be fetched for.
    if body.latitude is not None and body.longitude is not None:
        prefs.latitude = body.latitude
        prefs.longitude = body.longitude
        if body.location_label is not None:
            prefs.location_label = body.location_label.strip() or None
    elif body.location_label is not None and not body.location_label.strip():
        prefs.location_label = None
        prefs.latitude = None
        prefs.longitude = None
    db.commit()
    db.refresh(prefs)
    return serialize(prefs)


@router.get("/style", response_model=StyleProfileOut)
def read_style(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = get_profile(db, user)
    return StyleProfileOut(
        colors=split_tags(profile.colors),
        styles=split_tags(profile.styles),
        occasions=split_tags(profile.occasions),
        notes=profile.notes,
        available_colors=BASE_COLORS,
        available_styles=DEFAULT_STYLES,
        available_occasions=[
            o.name for o in db.query(OccasionOption).order_by(OccasionOption.position).all()
        ],
        identity=profile.identity,
        color_season=profile.color_season,
        aesthetics=split_tags(profile.aesthetics),
        necklines=split_tags(profile.necklines),
        silhouettes=split_tags(profile.silhouettes),
        fabrics=split_tags(profile.fabrics),
        mantra=profile.mantra,
    )


@router.put("/style", response_model=StyleProfileOut)
def write_style(
    body: StyleProfileIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = get_profile(db, user)
    if body.colors is not None:
        profile.colors = join_tags([c for c in body.colors if c in BASE_COLORS])
    if body.styles is not None:
        profile.styles = join_tags(body.styles)
    if body.occasions is not None:
        profile.occasions = join_tags(body.occasions)
    if body.notes is not None:
        profile.notes = body.notes.strip() or None

    # The descriptive half: stored as typed. No vocabulary is checked against
    # it on purpose — these are somebody's own conclusions about their own
    # shape, and the app has no list to correct them with. See
    # models.py:StyleProfile.
    if body.identity is not None:
        profile.identity = body.identity.strip() or None
    if body.color_season is not None:
        profile.color_season = body.color_season.strip() or None
    if body.aesthetics is not None:
        profile.aesthetics = join_tags(body.aesthetics)
    if body.necklines is not None:
        profile.necklines = join_tags(body.necklines)
    if body.silhouettes is not None:
        profile.silhouettes = join_tags(body.silhouettes)
    if body.fabrics is not None:
        profile.fabrics = join_tags(body.fabrics)
    if body.mantra is not None:
        profile.mantra = body.mantra.strip() or None

    db.commit()
    db.refresh(profile)
    return read_style(user, db)


@router.get("/style-guide", response_model=StyleGuideOut)
def style_guide(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """What this wardrobe's own colours go with, and where the holes are.

    Not generic fashion advice: every line is read off the installation's own
    colour rules (the ones a beheerder can edit) and the garments actually in
    the kast. Advice you can trace back to a rule is advice you can change.
    """
    require_view(db, wardrobe_id, user)
    items = db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()
    profile = get_profile(db, user)
    my_colors = {c.lower() for c in split_tags(profile.colors)}

    good_pairs, bad_pairs = load_pairs(db)
    counts = Counter()
    for it in items:
        base = normalize_color(it.color)
        if base:
            counts[base] += 1

    colors: list[GuideColor] = []
    for color, count in counts.most_common():
        goes = sorted(_partners(good_pairs, color))
        clashes = sorted(_partners(bad_pairs, color))
        if color in NEUTRALS:
            goes = ["(vrijwel alles — het is een neutrale tint)"]
        colors.append(
            GuideColor(
                color=color,
                count=count,
                goes_with=goes,
                clashes_with=clashes,
                in_profile=color in my_colors,
            )
        )

    # Where the wardrobe is thin. Deliberately phrased as an observation rather
    # than an instruction to go shopping.
    gaps: list[GuideGap] = []
    neutral_count = sum(n for c, n in counts.items() if c in NEUTRALS)
    if items and neutral_count < max(2, len(items) // 6):
        gaps.append(
            GuideGap(
                title="Weinig neutrale tinten",
                detail=(
                    "Neutrale kleuren (zwart, wit, grijs, beige, navy, denim)"
                    " combineren met vrijwel alles. Met een paar meer wordt de"
                    " rest van je kast makkelijker te combineren."
                ),
            )
        )
    untagged = [it for it in items if not it.occasion]
    if untagged:
        gaps.append(
            GuideGap(
                title=f"{len(untagged)} stuk(ken) zonder gelegenheid",
                detail=(
                    "Zonder gelegenheid weet de app niet wanneer een kledingstuk"
                    " past, dus doet het overal een beetje mee. Een paar tags"
                    " maken de suggesties merkbaar scherper."
                ),
            )
        )

    covered: set[str] = set()
    for it in items:
        covered.update(t.lower() for t in split_tags(it.weather))
    uncovered = [t for t in WEATHER_TAGS if t.lower() not in covered] if items else []

    tips = [
        "Neutrale tinten zijn de lijm van een kast: ze passen bij vrijwel alles.",
        "Ton-sur-ton (twee tinten van dezelfde kleur) werkt bijna altijd.",
        "Tag een kledingstuk voor het weer waarin je het echt draagt — dat is"
        " precies wat 'Vandaag' gebruikt om iets voor te stellen.",
    ]
    if my_colors:
        tips.append(
            "Je stijl-DNA staat ingesteld; outfits in jouw kleuren krijgen"
            " voorrang in de aanbevelingen."
        )

    return StyleGuideOut(
        colors=colors,
        neutrals=NEUTRALS,
        gaps=gaps,
        uncovered_weather=uncovered,
        tips=tips,
    )
