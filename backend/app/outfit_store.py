"""Reading and writing saved outfits.

Kept out of the routers because four screens need the same things — an outfit
with its garments, how often *you* wore it, when you last did — and a packing
list that disagrees with the planner about what an outfit contains would be
worse than either feature being absent.
"""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Item, Outfit, OutfitItem, WearLog
from .schemas import ItemOut, OutfitOut
from .tags import join_tags, split_tags


def get_outfit(db: Session, outfit_id: int) -> Outfit:
    outfit = db.get(Outfit, outfit_id)
    if outfit is None:
        raise HTTPException(status_code=404, detail="Outfit niet gevonden")
    return outfit


def wardrobe_outfits(db: Session, wardrobe_id: int) -> list[Outfit]:
    return (
        db.query(Outfit)
        .filter(Outfit.wardrobe_id == wardrobe_id)
        .order_by(Outfit.updated_at.desc())
        .all()
    )


def wear_index(db: Session, user_id: int, outfit_ids: list[int]) -> dict[int, list[str]]:
    """Every day each outfit was worn, newest first, for one user."""
    if not outfit_ids:
        return {}
    rows = (
        db.query(WearLog)
        .filter(WearLog.user_id == user_id, WearLog.outfit_id.in_(outfit_ids))
        .order_by(WearLog.worn_on.desc())
        .all()
    )
    index: dict[int, list[str]] = {}
    for row in rows:
        index.setdefault(row.outfit_id, []).append(row.worn_on)
    return index


def last_worn_map(db: Session, user_id: int, outfit_ids: list[int]) -> dict[int, str]:
    return {oid: days[0] for oid, days in wear_index(db, user_id, outfit_ids).items() if days}


def serialize(
    outfit: Outfit,
    wears: list[str] | None = None,
) -> OutfitOut:
    """One outfit as the API describes it, wear history included."""
    wears = wears or []
    return OutfitOut(
        id=outfit.id,
        name=outfit.name,
        notes=outfit.notes,
        items=[ItemOut.model_validate(it) for it in outfit.items],
        seasons=split_tags(outfit.season),
        occasions=split_tags(outfit.occasion),
        weather_tags=split_tags(outfit.weather),
        style_tags=split_tags(outfit.style),
        created_by_id=outfit.created_by_id,
        created_at=outfit.created_at,
        wear_count=len(wears),
        last_worn=wears[0] if wears else None,
    )


def serialize_many(
    db: Session,
    outfits: list[Outfit],
    user_id: int,
    with_wears: bool = True,
) -> list[OutfitOut]:
    index = wear_index(db, user_id, [o.id for o in outfits]) if with_wears else {}
    return [serialize(o, index.get(o.id, [])) for o in outfits]


def set_items(db: Session, outfit: Outfit, item_ids: list[int]) -> None:
    """Replace the garments in an outfit, keeping the order they were given in.

    Every garment has to live in the same kast as the outfit: an outfit that
    reached across wardrobes would show somebody else's clothes to everyone the
    kast is shared with.
    """
    seen: list[int] = []
    for item_id in item_ids:
        if item_id not in seen:
            seen.append(item_id)
    items = db.query(Item).filter(Item.id.in_(seen)).all() if seen else []
    by_id = {it.id: it for it in items}
    missing = [i for i in seen if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    foreign = [i for i in seen if by_id[i].wardrobe_id != outfit.wardrobe_id]
    if foreign:
        raise HTTPException(
            status_code=400, detail="Een outfit kan alleen kleding uit dezelfde kast bevatten"
        )

    outfit.entries.clear()
    db.flush()
    for position, item_id in enumerate(seen):
        outfit.entries.append(OutfitItem(item_id=item_id, position=position))


def apply_tags(outfit: Outfit, body) -> None:
    """Copy the tag lists off a request body onto the row."""
    outfit.season = join_tags(body.seasons)
    outfit.occasion = join_tags(body.occasions)
    outfit.weather = join_tags(body.weather_tags)
    outfit.style = join_tags(body.style_tags)


def log_wear(db: Session, outfit: Outfit, user_id: int, day: str | None = None) -> str:
    """Record that this user wore this outfit on ``day`` (default: today)."""
    worn_on = day or date.today().isoformat()
    existing = (
        db.query(WearLog)
        .filter(
            WearLog.outfit_id == outfit.id,
            WearLog.user_id == user_id,
            WearLog.worn_on == worn_on,
        )
        .first()
    )
    if existing is None:
        db.add(WearLog(outfit_id=outfit.id, user_id=user_id, worn_on=worn_on))
        db.commit()
    return worn_on


def unlog_wear(db: Session, outfit_id: int, user_id: int, day: str) -> None:
    db.query(WearLog).filter(
        WearLog.outfit_id == outfit_id,
        WearLog.user_id == user_id,
        WearLog.worn_on == day,
    ).delete()
    db.commit()
