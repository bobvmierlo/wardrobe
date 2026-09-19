"""Aanvullen: give an existing kast the tags and looks it never got.

Everything here is on request. Nothing runs on its own, nothing is overwritten,
and both actions can be undone by hand — see :mod:`app.autofill` for the rules
and for why the tagging is as cautious as it is.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import audit
from ..access import require_edit, require_view
from ..autofill import apply_tags, plan_looks, plan_tags
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, OccasionOption, Outfit, User
from ..outfit_store import apply_tags as apply_outfit_tags
from ..outfit_store import serialize, set_items, wardrobe_outfits
from ..routers.color_rules import load_pairs
from ..routers.matches import verdict_pairs, wardrobe_items
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
    )


@router.post("/tags", response_model=AutofillTagsResult)
def fill_tags(
    wardrobe_id: int,
    dry_run: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fill in the weather and occasion tags that are obvious from the category.

    Only ever fills a field that is empty. A garment somebody already tagged is
    left exactly as it is.
    """
    require_edit(db, wardrobe_id, user)
    items = db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()
    plans = plan_tags(items, _occasion_names(db))

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
        return AutofillTagsResult(tagged=len(plans), examples=examples)

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
    return AutofillTagsResult(tagged=tagged, examples=examples)


@router.post("/looks", response_model=AutofillLooksResult)
def compose_looks(
    wardrobe_id: int,
    count: int = Query(default=10, ge=1, le=MAX_LOOKS),
    dry_run: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build looks out of what is in the kast and save them.

    Uses the same scoring as everything else — the installation's own colour
    rules, season overlap, and never a pair anybody rejected. A look is tagged
    with what the garments in it agree on, so it claims nothing they do not.
    """
    require_edit(db, wardrobe_id, user)
    items, outfits, plans = _look_context(db, wardrobe_id, count)

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
    return AutofillLooksResult(created=[serialize(o) for o in created], note=note)
