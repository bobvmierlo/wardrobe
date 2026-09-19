"""Saved outfits, the wear log, and "je zou dit aan kunnen trekken".

An outfit here is a set of garments somebody decided on, with the tags that
say when to wear it. That is a different thing from a *combination*, which is
a verdict about two garments and lives under ``/api/matches`` — see the
docstring on :class:`app.models.Outfit` for why both exist.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import audit
from ..access import require_edit, require_view
from ..database import get_db
from ..deps import get_current_user
from ..models import Outfit, User
from ..preferences import as_weather_out, forecast_for, get_preferences, get_profile
from ..outfit_store import (
    apply_tags,
    get_outfit,
    last_worn_map,
    log_wear,
    serialize,
    serialize_many,
    set_items,
    unlog_wear,
    wardrobe_outfits,
    wear_index,
)
from ..recommendations import bare_skin_note, rank_saved, weather_advice
from ..routers.color_rules import load_pairs
from ..routers.matches import verdict_pairs, wardrobe_items
from ..schemas import (
    ItemOut,
    OutfitIn,
    OutfitOut,
    OutfitSuggestion,
    RecommendationOut,
    RecommendationPage,
    WearIn,
    WearOut,
)
from ..suggestions import suggest_outfits
from ..tags import split_tags

router = APIRouter(prefix="/api/outfits", tags=["outfits"])

#: How many suggestions the "Vandaag" screen asks for. Enough to choose from,
#: few enough that choosing is not itself a chore.
TODAY_LIMIT = 6


def _season_now(today: date | None = None) -> str:
    """The season we are in, by month. Good enough for a wardrobe."""
    month = (today or date.today()).month
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Lente"
    if month in (6, 7, 8):
        return "Zomer"
    return "Herfst"


# ---------------------------------------------------------------------------
# The screens that recommend something. Declared before "/{outfit_id}" so the
# path matcher never mistakes "recommendations" for an outfit id.
# ---------------------------------------------------------------------------

@router.get("/recommendations", response_model=RecommendationPage)
def recommendations(
    wardrobe_id: int,
    occasion: str | None = None,
    limit: int = Query(default=TODAY_LIMIT, ge=1, le=24),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """What to wear today, given the weather and (optionally) the occasion.

    Saved outfits are ranked first — a human already said these clothes go
    together — and the list is topped up with fresh combinations so a kast
    with no saved outfits yet still answers the question on day one.
    """
    require_view(db, wardrobe_id, user)
    prefs = get_preferences(db, user)
    profile = get_profile(db, user)
    forecast = forecast_for(prefs)
    weather_tags = list(forecast.tags) if forecast else []
    season = _season_now()

    outfits = wardrobe_outfits(db, wardrobe_id)
    last_worn = (
        last_worn_map(db, user.id, [o.id for o in outfits])
        if prefs.wear_log_enabled
        else {}
    )
    ranked = rank_saved(
        outfits,
        weather_tags,
        occasion,
        season=season,
        last_worn=last_worn,
        style_colors=split_tags(profile.colors),
        style_words=split_tags(profile.styles),
    )

    results = [
        RecommendationOut(
            items=[ItemOut.model_validate(it) for it in rec.items],
            score=rec.score,
            reason=rec.reason,
            source="saved",
            outfit_id=rec.outfit.id if rec.outfit else None,
            outfit_name=rec.outfit.name if rec.outfit else None,
            last_worn=rec.last_worn,
        )
        for rec in ranked[:limit]
    ]

    # Top up with freshly built combinations when there are not enough saved
    # outfits that suit today.
    if len(results) < limit:
        for suggestion in _build(db, wardrobe_id, occasion, weather_tags, limit - len(results)):
            results.append(
                RecommendationOut(
                    items=suggestion["items"],
                    score=suggestion["score"],
                    reason=suggestion["reason"],
                    source="new",
                )
            )

    empty_reason = None
    if not results:
        if not wardrobe_items(db, wardrobe_id):
            empty_reason = "Er zit nog niets in deze kast."
        else:
            empty_reason = (
                "Niets gevonden dat bij dit weer en deze gelegenheid past."
                " Tag wat kledingstukken, of kies een andere gelegenheid."
            )

    # Twee zinnen kunnen: wat het weer doet, en — als jouw voorkeur daar iets
    # aan verandert — of er voor jou nog een korte broek in zit.
    advice = weather_advice(weather_tags) if weather_tags else ""
    personal = bare_skin_note(
        forecast.apparent_temperature if forecast else None,
        prefs.temperature_preference,
    )
    if personal:
        advice = f"{advice} {personal}".strip()

    return RecommendationPage(
        weather=as_weather_out(forecast, prefs.weather_mode or "auto"),
        advice=advice,
        occasion=occasion,
        recommendations=results,
        empty_reason=empty_reason,
    )


@router.get("/discover", response_model=list[OutfitSuggestion])
def discover(
    wardrobe_id: int,
    occasion: str | None = None,
    season: str | None = None,
    weather: str | None = Query(default=None, description="Comma-separated weather tags"),
    limit: int = Query(default=12, ge=1, le=40),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build outfits to order: pick an occasion, a season and the weather.

    The "Ontdekken" screen. Unlike the recommendations above this ignores what
    is saved and what you wore lately — it is for browsing what the wardrobe
    *could* do, not for deciding what to put on in ten minutes.
    """
    require_view(db, wardrobe_id, user)
    weather_tags = split_tags(weather)
    built = _build(db, wardrobe_id, occasion, weather_tags, limit, season=season)
    return [
        OutfitSuggestion(items=b["items"], score=b["score"], reason=b["reason"])
        for b in built
    ]


def _build(
    db: Session,
    wardrobe_id: int,
    occasion: str | None,
    weather_tags: list[str],
    limit: int,
    season: str | None = None,
) -> list[dict]:
    """Fresh combinations from the wardrobe, respecting everyone's verdicts."""
    items = wardrobe_items(db, wardrobe_id)
    if season:
        items = [it for it in items if not it.season or season.lower() in (it.season or "").lower()]
    if len(items) < 2:
        return []
    rejected, approved = verdict_pairs(db, {it.id for it in items})
    good_pairs, bad_pairs = load_pairs(db)
    built = suggest_outfits(
        items,
        rejected,
        approved,
        limit=limit,
        good_pairs=good_pairs,
        bad_pairs=bad_pairs,
        occasion=occasion,
        weather_tags=weather_tags,
    )
    return [
        {
            "items": [ItemOut.model_validate(it) for it in b["items"]],
            "score": b["score"],
            "reason": b["reason"],
        }
        for b in built
    ]


# ---------------------------------------------------------------------------
# The outfits themselves
# ---------------------------------------------------------------------------

@router.get("", response_model=list[OutfitOut])
def list_outfits(
    wardrobe_id: int,
    occasion: str | None = None,
    weather: str | None = None,
    season: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, wardrobe_id, user)
    outfits = wardrobe_outfits(db, wardrobe_id)
    if occasion:
        outfits = [o for o in outfits if occasion.lower() in (o.occasion or "").lower()]
    if weather:
        outfits = [o for o in outfits if weather.lower() in (o.weather or "").lower()]
    if season:
        outfits = [o for o in outfits if season.lower() in (o.season or "").lower()]
    return serialize_many(db, outfits, user.id)


@router.post("", response_model=OutfitOut, status_code=201)
def create_outfit(
    body: OutfitIn,
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_edit(db, wardrobe_id, user)
    outfit = Outfit(
        name=body.name.strip(),
        notes=(body.notes or "").strip() or None,
        wardrobe_id=wardrobe_id,
        created_by_id=user.id,
    )
    apply_tags(outfit, body)
    db.add(outfit)
    db.flush()
    set_items(db, outfit, body.item_ids)
    db.commit()
    db.refresh(outfit)
    audit.record(
        db,
        "outfit.create",
        f"Outfit '{outfit.name}' met {len(outfit.entries)} stuk(ken) opgeslagen",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="outfit",
        entity_id=outfit.id,
    )
    return serialize(outfit)


@router.get("/{outfit_id}", response_model=OutfitOut)
def get_one(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outfit = get_outfit(db, outfit_id)
    require_view(db, outfit.wardrobe_id, user)
    return serialize(outfit, wear_index(db, user.id, [outfit.id]).get(outfit.id, []))


@router.put("/{outfit_id}", response_model=OutfitOut)
def update_outfit(
    outfit_id: int,
    body: OutfitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outfit = get_outfit(db, outfit_id)
    require_edit(db, outfit.wardrobe_id, user)
    outfit.name = body.name.strip()
    outfit.notes = (body.notes or "").strip() or None
    apply_tags(outfit, body)
    set_items(db, outfit, body.item_ids)
    db.commit()
    db.refresh(outfit)
    audit.record(
        db,
        "outfit.update",
        f"Outfit '{outfit.name}' gewijzigd",
        user=user,
        wardrobe_id=outfit.wardrobe_id,
        entity_type="outfit",
        entity_id=outfit.id,
    )
    return serialize(outfit, wear_index(db, user.id, [outfit.id]).get(outfit.id, []))


@router.delete("/{outfit_id}", status_code=204)
def delete_outfit(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outfit = get_outfit(db, outfit_id)
    require_edit(db, outfit.wardrobe_id, user)
    name, wardrobe_id = outfit.name, outfit.wardrobe_id
    db.delete(outfit)
    db.commit()
    audit.record(
        db,
        "outfit.delete",
        f"Outfit '{name}' verwijderd",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="outfit",
        entity_id=outfit_id,
    )


# ---------------------------------------------------------------------------
# The wear log, which only exists for people who asked for one
# ---------------------------------------------------------------------------

def _require_wear_log(db: Session, user: User) -> None:
    prefs = get_preferences(db, user)
    if not prefs.wear_log_enabled:
        raise HTTPException(
            status_code=409,
            detail="Het draaglogboek staat uit. Zet het aan bij Instellingen.",
        )


@router.post("/{outfit_id}/wear", response_model=WearOut, status_code=201)
def wear(
    outfit_id: int,
    body: WearIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Note that you wore this outfit today (or on a given day).

    Viewing rights are enough: what *you* wore is your own record, and someone
    with a kijker's access to a shared kast still dresses out of it.
    """
    outfit = get_outfit(db, outfit_id)
    require_view(db, outfit.wardrobe_id, user)
    _require_wear_log(db, user)
    worn_on = log_wear(db, outfit, user.id, body.worn_on if body else None)
    return WearOut(outfit_id=outfit.id, worn_on=worn_on)


@router.delete("/{outfit_id}/wear/{day}", status_code=204)
def unwear(
    outfit_id: int,
    day: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outfit = get_outfit(db, outfit_id)
    require_view(db, outfit.wardrobe_id, user)
    unlog_wear(db, outfit.id, user.id, day)


@router.get("/{outfit_id}/wear", response_model=list[str])
def wear_history(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The days *you* wore this outfit. Never anybody else's history."""
    outfit = get_outfit(db, outfit_id)
    require_view(db, outfit.wardrobe_id, user)
    return wear_index(db, user.id, [outfit.id]).get(outfit.id, [])
