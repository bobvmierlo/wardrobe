"""Aanvullen: give an existing kast the tags and looks it never got.

Everything here is on request. Nothing runs on its own, nothing is overwritten,
and both actions can be undone by hand — see :mod:`app.autofill` for the rules
and for why the tagging is as cautious as it is.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import ai as ai_layer
from .. import ai_usage
from .. import app_settings
from .. import audit
from ..access import require_edit, require_view
from ..autofill import TagPlan, apply_tags, plan_looks, plan_tags, validate_ai_looks
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, OccasionOption, Outfit, User
from ..outfit_store import apply_tags as apply_outfit_tags
from ..outfit_store import serialize, set_items, wardrobe_outfits
from ..routers.color_rules import load_pairs
from ..matching import group_of
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

#: How far the preview counts before it gives up and says "meer dan dit".
#:
#: The preview used to count only as far as the largest batch the button
#: offers, so a kast with hundreds of untried combinations reported exactly as
#: many as you could make in one press — and kept reporting that number after
#: every press, because there were always at least that many left. The count
#: and the batch are two different questions, so this is a separate, much
#: larger number: it is what "er zijn er nog N te maken" actually means.
#:
#: Not unbounded. :func:`app.suggestions.suggest_outfits` already builds every
#: top/bottom combination the kast allows, so counting further is cheap but not
#: free, and past a couple of hundred "nog heel veel" is the honest answer
#: anyway.
COUNT_CAP = 300


def _occasion_names(db: Session) -> list[str]:
    return [
        o.name
        for o in db.query(OccasionOption)
        .order_by(OccasionOption.position, OccasionOption.name)
        .all()
    ]


def _why_nothing(db: Session, items: list[Item], outfits: list) -> str:
    """Waarom er geen enkele nieuwe look te maken valt.

    Bestaat omdat een uitgegrijsde knop zonder reden iemand naar een storing
    laat zoeken die er niet is: een kast met twee kledingstukken waarvan de
    enige combinatie al bewaard is, is geen fout maar een kast met twee
    kledingstukken.
    """
    if len(items) < 2:
        return "Er zit nog te weinig in deze kast om iets te combineren."

    groups = {group_of(it.category) for it in items}
    has_base = "dress" in groups or ("top" in groups and "bottom" in groups)
    if not has_base:
        return (
            "Er is wel kleding, maar geen bovenstuk met een onderstuk (of een"
            " jurk) om een outfit van te maken."
        )

    rejected, _approved = verdict_pairs(db, {it.id for it in items})
    if outfits:
        return (
            "Alles wat in deze kast past, staat al als look opgeslagen."
            " Voeg kleding toe voor nieuwe combinaties."
        )
    if rejected:
        return (
            "Elke mogelijke combinatie is bij het combineren afgekeurd."
            " Trek daar een oordeel in, of voeg kleding toe."
        )
    return "Geen combinaties gevonden die bij elkaar passen."


def _look_context(db: Session, wardrobe_id: int, count: int, seed: list | None = None):
    """Everything :func:`app.autofill.plan_looks` needs, read once.

    ``seed`` holds looks that are already going to be created this run (the
    AI's, when it ran): their garment sets and names count as taken, so the
    app's own top-up cannot duplicate them.
    """
    items = wardrobe_items(db, wardrobe_id)
    outfits = wardrobe_outfits(db, wardrobe_id)
    existing = {frozenset(it.id for it in o.items) for o in outfits}
    taken = {o.name.lower() for o in outfits}
    for plan in seed or []:
        existing.add(frozenset(it.id for it in plan.items))
        taken.add(plan.name.lower())
    if count <= 0:
        return items, outfits, []
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """What both buttons would do. Changes nothing.

    Takes no batch size, unlike the button it describes: how many looks there
    are left to make and how many you want in one go are two different
    questions, and answering the first with the second is what made the screen
    say "er zijn er nog 20 te maken" to every kast forever. See
    :data:`COUNT_CAP`.
    """
    require_view(db, wardrobe_id, user)
    items, outfits, plans = _look_context(db, wardrobe_id, COUNT_CAP)
    tag_plans = plan_tags(items, _occasion_names(db))
    return AutofillPreview(
        composable_reason=_why_nothing(db, items, outfits) if not plans else None,
        item_count=len(items),
        without_weather=sum(1 for it in items if not (it.weather or "").strip()),
        without_occasion=sum(1 for it in items if not (it.occasion or "").strip()),
        taggable=len(tag_plans),
        outfit_count=len(outfits),
        composable=len(plans),
        composable_capped=len(plans) >= COUNT_CAP,
        ai_available=app_settings.ai_config(db).usable,
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
    calls: list[ai_layer.AiCall] = []
    if use_ai:
        extra, ai_note = _ai_tag_plans(
            app_settings.ai_config(db), items, plans, occasions, calls
        )
        by_ai = len(extra)
        plans = plans + extra
    # Ook bij een proefdraai: het verzoek is verstuurd en wordt dus berekend.
    ai_usage.record(db, calls, user)

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
    config: app_settings.AiConfig,
    items: list[Item],
    rule_plans: list[TagPlan],
    occasions: list[str],
    usage: list[ai_layer.AiCall],
) -> tuple[list[TagPlan], str | None]:
    """Ask the model about the garments the rules left untouched.

    Deliberately narrow: a garment the rules already answered for is not even
    sent, so the model can never overrule them — and, like the rules, an empty
    field is the only thing it may fill.
    """
    if not config.usable:
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
        suggestions = ai_layer.suggest_tags(
            config, remaining, occasions, WEATHER_TAGS, usage=usage
        )
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


def _ai_look_plans(
    db: Session,
    config: app_settings.AiConfig,
    wardrobe_id: int,
    outfits: list,
    count: int,
    usage: list[ai_layer.AiCall],
) -> tuple[list, int, str | None]:
    """Let the model compose looks, then hold every proposal to the kast's rules.

    The model is told which pairs were approved and which were rejected, so it
    *can* take them into account. Whether it *did* is not taken on trust:
    :func:`app.autofill.validate_ai_looks` throws out anything that pairs two
    garments somebody said no to, and says how many it threw out.
    """
    items = wardrobe_items(db, wardrobe_id)
    if len(items) < 2:
        return [], 0, None

    rejected, approved = verdict_pairs(db, {it.id for it in items})
    existing = {frozenset(it.id for it in o.items) for o in outfits}
    taken = {o.name.lower() for o in outfits}

    try:
        proposals = ai_layer.compose_looks(
            config,
            items,
            approved,
            rejected,
            existing,
            _occasion_names(db),
            WEATHER_TAGS,
            count,
            usage=usage,
        )
    except ai_layer.AiUnavailable as exc:
        return [], 0, str(exc)

    review = validate_ai_looks(
        proposals, {it.id: it for it in items}, rejected, existing, taken
    )
    accepted = review.accepted[:count]
    return accepted, len(accepted), review.summary()


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

    With ``use_ai`` the model composes the looks itself. It is told which pairs
    the household approved and which they rejected — but that it took them into
    account is never assumed: every proposal goes through
    :func:`app.autofill.validate_ai_looks`, which throws out any outfit pairing
    two garments somebody said no to, and reports how many it threw out. A
    rejected pair can therefore not come back because a model liked the look of
    it, whatever the model answers.

    Whatever the AI does not deliver — because it was off, unreachable, or its
    proposals did not survive the check — the app composes itself, so the button
    always does something.
    """
    require_edit(db, wardrobe_id, user)

    by_ai, ai_note = 0, None
    plans: list = []
    calls: list[ai_layer.AiCall] = []

    if use_ai:
        config = app_settings.ai_config(db)
        if not config.usable:
            ai_note = "De AI-laag staat uit in deze installatie."
        else:
            outfits = wardrobe_outfits(db, wardrobe_id)
            plans, by_ai, ai_note = _ai_look_plans(
                db, config, wardrobe_id, outfits, count, calls
            )
    ai_usage.record(db, calls, user)

    # De app vult aan wat de AI niet leverde — of doet alles, als die uitstaat.
    items, outfits, own = _look_context(
        db, wardrobe_id, max(count - len(plans), 0), seed=plans
    )
    plans = plans + own

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
            by_ai=by_ai,
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
        by_ai=by_ai,
        ai_note=ai_note,
    )
