"""Aanvullen: give an existing kast the tags and looks it never got.

Everything here is on request. Nothing runs on its own, nothing is overwritten,
and both actions can be undone by hand — see :mod:`app.autofill` for the rules
and for why the tagging is as cautious as it is.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import ai as ai_layer
from .. import audit
from ..access import require_edit, require_view
from ..autofill import TagPlan, apply_tags, plan_looks, plan_tags
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, OccasionOption, Outfit, User
from ..outfit_store import apply_tags as apply_outfit_tags
from ..outfit_store import serialize, set_items, wardrobe_outfits
from ..routers.color_rules import load_pairs
from ..routers.matches import verdict_pairs, wardrobe_items
from ..tags import WEATHER_TAGS, split_tags
from ..schemas import (
    AutofillLooksResult,
    AutofillPreview,
    AutofillTagsResult,
    ComposedLook,
    ItemOut,
    OutfitIn,
    TaggedItem,
)

router = APIRouter(prefix="/api/autofill", tags=["autofill"])

#: Most anyone wants in one go. A hundred looks nobody asked for is not a
#: filled wardrobe, it is a mess to clean up.
MAX_LOOKS = 40


def _occasion_names(db: Session) -> list[str]:
    return [
        o.name
        for o in db.query(OccasionOption)
        .order_by(OccasionOption.position, OccasionOption.name)
        .all()
    ]


def _look_context(db: Session, wardrobe_id: int, count: int):
    """Everything :func:`app.autofill.plan_looks` needs, read once."""
    items = wardrobe_items(db, wardrobe_id)
    outfits = wardrobe_outfits(db, wardrobe_id)
    existing = {frozenset(it.id for it in o.items) for o in outfits}
    taken = {o.name.lower() for o in outfits}
    rejected, approved = verdict_pairs(db, {it.id for it in items})
    good_pairs, bad_pairs = load_pairs(db)
    plans = plan_looks(
        items,
        rejected,
        approved,
        existing,
        taken,
        count,
        good_pairs=good_pairs,
        bad_pairs=bad_pairs,
    )
    return items, outfits, plans


@router.get("/preview", response_model=AutofillPreview)
def preview(
    wardrobe_id: int,
    count: int = Query(default=10, ge=1, le=MAX_LOOKS),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """What both buttons would do. Changes nothing."""
    require_view(db, wardrobe_id, user)
    items, outfits, plans = _look_context(db, wardrobe_id, count)
    tag_plans = plan_tags(items, _occasion_names(db))
    return AutofillPreview(
        item_count=len(items),
        without_weather=sum(1 for it in items if not (it.weather or "").strip()),
        without_occasion=sum(1 for it in items if not (it.occasion or "").strip()),
        taggable=len(tag_plans),
        outfit_count=len(outfits),
        composable=len(plans),
        ai_available=ai_layer.is_configured(),
    )


@router.post("/tags", response_model=AutofillTagsResult)
def fill_tags(
    wardrobe_id: int,
    dry_run: bool = False,
    use_ai: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fill in the weather and occasion tags that are obvious from the category.

    Only ever fills a field that is empty. A garment somebody already tagged is
    left exactly as it is.

    With ``use_ai`` the rules still run first and still win; the model is only
    asked about the garments they had nothing to say about, and everything it
    answers is filtered against this installation's own lists. See app/ai.py.
    """
    require_edit(db, wardrobe_id, user)
    items = db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()
    occasions = _occasion_names(db)
    plans = plan_tags(items, occasions)

    by_ai, ai_note = 0, None
    if use_ai:
        extra, ai_note = _ai_tag_plans(items, plans, occasions)
        by_ai = len(extra)
        plans = plans + extra

    examples = [
        TaggedItem(
            id=plan.item.id,
            name=plan.item.name,
            category=plan.item.category,
            weather=plan.weather,
            occasions=plan.occasions,
        )
        for plan in plans[:8]
    ]
    if dry_run:
        return AutofillTagsResult(
            tagged=len(plans), examples=examples, by_ai=by_ai, ai_note=ai_note
        )

    tagged = apply_tags(plans)
    db.commit()
    if tagged:
        audit.record(
            db,
            "item.autotag",
            f"{tagged} kledingstuk(ken) automatisch getagd (weer en gelegenheid)",
            user=user,
            wardrobe_id=wardrobe_id,
            entity_type="item",
        )
    return AutofillTagsResult(
        tagged=tagged, examples=examples, by_ai=by_ai, ai_note=ai_note
    )


def _ai_tag_plans(
    items: list[Item],
    rule_plans: list[TagPlan],
    occasions: list[str],
) -> tuple[list[TagPlan], str | None]:
    """Ask the model about the garments the rules left untouched.

    Deliberately narrow: a garment the rules already answered for is not even
    sent, so the model can never overrule them — and, like the rules, an empty
    field is the only thing it may fill.
    """
    if not ai_layer.is_configured():
        return [], "De AI-laag staat uit in deze installatie."

    settled = {plan.item.id for plan in rule_plans}
    remaining = [
        item
        for item in items
        if item.id not in settled
        and (not split_tags(item.occasion) or not split_tags(item.weather))
    ]
    if not remaining:
        return [], None

    try:
        suggestions = ai_layer.suggest_tags(remaining, occasions, WEATHER_TAGS)
    except ai_layer.AiUnavailable as exc:
        return [], str(exc)

    by_id = {item.id: item for item in remaining}
    plans: list[TagPlan] = []
    for suggestion in suggestions:
        item = by_id.get(suggestion.item_id)
        if item is None:
            continue
        plan = TagPlan(item=item)
        # Still only empty fields, exactly as the rules do it.
        if suggestion.occasions and not split_tags(item.occasion):
            plan.occasions = suggestion.occasions
        if suggestion.weather and not split_tags(item.weather):
            plan.weather = suggestion.weather
        if plan.changes:
            plans.append(plan)
    return plans, None


@router.post("/looks", response_model=AutofillLooksResult)
def compose_looks(
    wardrobe_id: int,
    count: int = Query(default=10, ge=1, le=MAX_LOOKS),
    dry_run: bool = False,
    use_ai: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build looks out of what is in the kast and save them.

    Uses the same scoring as everything else — the installation's own colour
    rules, season overlap, and never a pair anybody rejected. A look is tagged
    with what the garments in it agree on, so it claims nothing they do not.

    ``use_ai`` changes **only the names**. Which garments end up together stays
    the app's own decision, because that is the part with rules behind it: a
    pair somebody rejected must never reappear because a model liked the look
    of it.
    """
    require_edit(db, wardrobe_id, user)
    items, outfits, plans = _look_context(db, wardrobe_id, count)

    named_by_ai, ai_note = 0, None
    if use_ai and plans:
        if not ai_layer.is_configured():
            ai_note = "De AI-laag staat uit in deze installatie."
        else:
            try:
                taken = {o.name.lower() for o in outfits}
                names = ai_layer.name_looks([plan.items for plan in plans])
                for index, name in names.items():
                    if name.lower() in taken:
                        continue  # botst met een bestaande look; app-naam blijft
                    taken.add(name.lower())
                    plans[index].name = name
                    named_by_ai += 1
            except ai_layer.AiUnavailable as exc:
                ai_note = str(exc)

    note = None
    if len(items) < 2:
        note = "Er zit te weinig in deze kast om iets te combineren."
    elif not plans:
        note = (
            "Geen nieuwe combinaties gevonden. Waarschijnlijk staat alles wat"
            " past al als look opgeslagen."
        )
    elif len(plans) < count:
        note = (
            f"{len(plans)} van de {count} gevraagde looks gemaakt — meer"
            " combinaties leverde deze kast niet op zonder in herhaling te vallen."
        )

    if dry_run:
        return AutofillLooksResult(
            proposed=[
                ComposedLook(
                    name=plan.name,
                    items=[ItemOut.model_validate(it) for it in plan.items],
                    seasons=plan.seasons,
                    occasions=plan.occasions,
                    weather_tags=plan.weather,
                    style_tags=plan.styles,
                    reason=plan.reason,
                )
                for plan in plans
            ],
            note=note,
            named_by_ai=named_by_ai,
            ai_note=ai_note,
        )

    created = []
    for plan in plans:
        outfit = Outfit(
            name=plan.name,
            notes=plan.reason or None,
            wardrobe_id=wardrobe_id,
            created_by_id=user.id,
        )
        apply_outfit_tags(
            outfit,
            OutfitIn(
                name=plan.name,
                item_ids=[it.id for it in plan.items],
                seasons=plan.seasons,
                occasions=plan.occasions,
                weather_tags=plan.weather,
                style_tags=plan.styles,
            ),
        )
        db.add(outfit)
        db.flush()
        set_items(db, outfit, [it.id for it in plan.items])
        created.append(outfit)
    db.commit()

    if created:
        audit.record(
            db,
            "outfit.autocompose",
            f"{len(created)} look(s) automatisch samengesteld",
            user=user,
            wardrobe_id=wardrobe_id,
            entity_type="outfit",
        )
    for outfit in created:
        db.refresh(outfit)
    return AutofillLooksResult(
        created=[serialize(o) for o in created],
        note=note,
        named_by_ai=named_by_ai,
        ai_note=ai_note,
    )
