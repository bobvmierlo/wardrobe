"""Inzichten: what is actually in this kast, and what never leaves it.

Every number here is counted on the spot rather than kept up to date
somewhere, because a wardrobe is small and a statistic that can drift is worse
than one that costs a query.
"""

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..access import require_view
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, User, WearLog
from ..outfit_store import serialize, wardrobe_outfits, wear_index
from ..preferences import get_preferences
from ..schemas import ColorSlice, CountEntry, InsightsOut, ItemOut
from ..suggestions import normalize_color
from ..tags import split_tags

router = APIRouter(prefix="/api/insights", tags=["insights"])

#: Not worn in this long counts as neglected — the "Opruimen" list. Long
#: enough that a coat is not flagged every summer.
NEGLECTED_DAYS = 180
#: A garment added recently has not had its chance yet, wear log or not.
GRACE_DAYS = 60


@router.get("", response_model=InsightsOut)
def insights(
    wardrobe_id: int,
    neglected_days: int = Query(default=NEGLECTED_DAYS, ge=30, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, wardrobe_id, user)
    items = db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()
    outfits = wardrobe_outfits(db, wardrobe_id)
    prefs = get_preferences(db, user)

    in_outfits: set[int] = set()
    for outfit in outfits:
        in_outfits.update(it.id for it in outfit.items)

    by_category = Counter(it.category for it in items)
    by_season: Counter = Counter()
    by_occasion: Counter = Counter()
    palette: Counter = Counter()
    for it in items:
        by_season.update(split_tags(it.season))
        by_occasion.update(split_tags(it.occasion))
        base = normalize_color(it.color)
        if base:
            palette[base] += 1

    wears = wear_index(db, user.id, [o.id for o in outfits]) if prefs.wear_log_enabled else {}
    total_wears = sum(len(days) for days in wears.values())
    most_worn = sorted(outfits, key=lambda o: len(wears.get(o.id, [])), reverse=True)
    most_worn = [o for o in most_worn if wears.get(o.id)][:5]

    return InsightsOut(
        item_count=len(items),
        outfit_count=len(outfits),
        favorite_count=sum(1 for it in items if it.is_favorite),
        unused_items=[
            ItemOut.model_validate(it) for it in items if it.id not in in_outfits
        ],
        by_category=[CountEntry(label=k, count=v) for k, v in by_category.most_common()],
        by_season=[CountEntry(label=k, count=v) for k, v in by_season.most_common()],
        by_occasion=[CountEntry(label=k, count=v) for k, v in by_occasion.most_common()],
        palette=[ColorSlice(color=k, count=v) for k, v in palette.most_common()],
        wear_log_enabled=bool(prefs.wear_log_enabled),
        total_wears=total_wears,
        most_worn=[serialize(o, wears.get(o.id, [])) for o in most_worn],
        neglected=[
            ItemOut.model_validate(it)
            for it in _neglected(
                items, outfits, wears, neglected_days, bool(prefs.wear_log_enabled)
            )
        ],
    )


def _neglected(
    items: list[Item],
    outfits: list,
    wears: dict[int, list[str]],
    neglected_days: int,
    wear_log_enabled: bool,
) -> list[Item]:
    """Garments that have not been near a body in a long time.

    Two different questions, depending on what there is to go on:

    * **With a wear log** it is a fact — the last day an outfit containing the
      garment was worn, or never. A garment sitting in a look nobody has worn
      is exactly the case this list exists for, so being in a look is no
      excuse here.
    * **Without one** it can only be inferred from how long ago the garment was
      added and whether it ever made it into a look at all. Weaker, and the
      screen says so rather than pretending otherwise — which is also why a
      garment that *is* in a look is left alone: without a log there is nothing
      to suggest it goes unworn.

    Either way a garment added recently is skipped: it has not had its chance.
    """
    today = date.today()
    last_worn_by_item: dict[int, str] = {}
    for outfit in outfits:
        days = wears.get(outfit.id)
        if not days:
            continue
        for item in outfit.items:
            current = last_worn_by_item.get(item.id)
            if current is None or days[0] > current:
                last_worn_by_item[item.id] = days[0]

    in_outfits: set[int] = set()
    for outfit in outfits:
        in_outfits.update(it.id for it in outfit.items)

    result: list[Item] = []
    for item in items:
        age = (today - item.created_at.date()).days if item.created_at else 0
        if age < GRACE_DAYS:
            continue  # too new to judge
        worn = last_worn_by_item.get(item.id)
        if worn:
            try:
                if (today - date.fromisoformat(worn)).days > neglected_days:
                    result.append(item)
            except ValueError:
                continue
        elif wear_log_enabled or item.id not in in_outfits:
            result.append(item)
    return result


@router.get("/wear-log", response_model=list[dict])
def wear_log(
    wardrobe_id: int,
    limit: int = Query(default=60, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Your own wear log for this kast, newest first. Never anybody else's."""
    require_view(db, wardrobe_id, user)
    outfits = {o.id: o for o in wardrobe_outfits(db, wardrobe_id)}
    if not outfits:
        return []
    rows = (
        db.query(WearLog)
        .filter(WearLog.user_id == user.id, WearLog.outfit_id.in_(list(outfits)))
        .order_by(WearLog.worn_on.desc())
        .limit(limit)
        .all()
    )
    return [
        {"worn_on": row.worn_on, "outfit_id": row.outfit_id, "name": outfits[row.outfit_id].name}
        for row in rows
        if row.outfit_id in outfits
    ]
