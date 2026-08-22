from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..access import require_view
from ..database import get_db
from ..deps import get_current_user
from ..matching import can_combine, is_cross_group, seasons_compatible
from ..models import Item, Match, User
from ..routers.color_rules import load_pairs
from ..schemas import ItemOut, MatchCreate, OutfitPartner, OutfitSuggestion, PairOut
from ..suggestions import suggest_outfits

router = APIRouter(prefix="/api/matches", tags=["matches"])


def _ordered(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _wardrobe_items(db: Session, wardrobe_id: int) -> list[Item]:
    return db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()


def _judged_pairs(db: Session, user_id: int, item_ids: set[int]) -> set[frozenset[int]]:
    rows = db.query(Match.item_a_id, Match.item_b_id).filter(Match.user_id == user_id).all()
    return {frozenset((a, b)) for a, b in rows if a in item_ids and b in item_ids}


@router.get("/next", response_model=PairOut | None)
def next_pair(
    wardrobe_id: int,
    anchor_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the next pair for the current user to judge, within one wardrobe.

    Pass ``anchor_id`` to keep swiping candidates for one garment. Omit it to
    let the server pick the garment with the most work left.
    """
    require_view(db, wardrobe_id, user)
    items = _wardrobe_items(db, wardrobe_id)
    if len(items) < 2:
        return None
    by_id = {it.id: it for it in items}
    judged = _judged_pairs(db, user.id, set(by_id))

    def candidates_for(anchor: Item) -> list[Item]:
        cands = [
            it for it in items
            if it.id != anchor.id
            and frozenset((anchor.id, it.id)) not in judged
            and seasons_compatible(anchor.season, it.season)
            and can_combine(anchor.category, it.category)
        ]
        # Cross-group pairs first, then most-recently-added.
        cands.sort(key=lambda it: (not is_cross_group(anchor.category, it.category), -it.id))
        return cands

    if anchor_id is not None:
        anchor = by_id.get(anchor_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Ankerstuk niet gevonden")
        cands = candidates_for(anchor)
        if not cands:
            return None
        return PairOut(anchor=ItemOut.model_validate(anchor),
                       candidate=ItemOut.model_validate(cands[0]))

    # No anchor: choose the item with the most unjudged candidates.
    best_anchor = None
    best_cands: list[Item] = []
    for anchor in items:
        cands = candidates_for(anchor)
        if len(cands) > len(best_cands):
            best_anchor, best_cands = anchor, cands
    if best_anchor is None or not best_cands:
        return None
    return PairOut(anchor=ItemOut.model_validate(best_anchor),
                   candidate=ItemOut.model_validate(best_cands[0]))


@router.post("", status_code=204)
def submit_verdict(
    body: MatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.item_a_id == body.item_b_id:
        raise HTTPException(status_code=400, detail="Een stuk kan niet met zichzelf gecombineerd worden")
    a, b = _ordered(body.item_a_id, body.item_b_id)
    item_a, item_b = db.get(Item, a), db.get(Item, b)
    if not item_a or not item_b:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    if item_a.wardrobe_id != item_b.wardrobe_id:
        raise HTTPException(status_code=400, detail="Stukken uit verschillende kasten")
    # A viewer may vote, so view access is enough here.
    require_view(db, item_a.wardrobe_id, user)

    existing = (
        db.query(Match)
        .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
        .first()
    )
    if existing:
        existing.verdict = body.verdict
    else:
        db.add(Match(item_a_id=a, item_b_id=b, user_id=user.id, verdict=body.verdict))
    db.commit()
    return Response(status_code=204)


@router.delete("/{item_a_id}/{item_b_id}", status_code=204)
def reset_pair(
    item_a_id: int,
    item_b_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the current user's verdict for a pair, so it can be judged again."""
    a, b = _ordered(item_a_id, item_b_id)
    item_a = db.get(Item, a)
    if item_a is not None:
        require_view(db, item_a.wardrobe_id, user)
    db.query(Match).filter(
        Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id
    ).delete()
    db.commit()


@router.get("/outfits/{item_id}", response_model=list[OutfitPartner])
def outfits_for(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Items approved to combine with the given item.

    A partner is approved when at least one member of the wardrobe said 'yes'
    and nobody said 'no'.
    """
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_view(db, item.wardrobe_id, user)

    # Only consider partners within the same wardrobe.
    partner_ids_in_wardrobe = {
        it.id for it in _wardrobe_items(db, item.wardrobe_id)
    }
    rows = (
        db.query(Match)
        .filter((Match.item_a_id == item_id) | (Match.item_b_id == item_id))
        .all()
    )
    # partner_id -> {"yes": set(user_id), "no": set(user_id)}
    verdicts: dict[int, dict[str, set[int]]] = {}
    for m in rows:
        partner_id = m.item_b_id if m.item_a_id == item_id else m.item_a_id
        if partner_id not in partner_ids_in_wardrobe:
            continue
        verdicts.setdefault(partner_id, {"yes": set(), "no": set()})
        verdicts[partner_id][m.verdict].add(m.user_id)

    approved_partner_ids = [
        pid for pid, v in verdicts.items() if v["yes"] and not v["no"]
    ]
    if not approved_partner_ids:
        return []

    users = {u.id: u.display_name for u in db.query(User).all()}
    partners = {it.id: it for it in db.query(Item).filter(Item.id.in_(approved_partner_ids)).all()}

    result: list[OutfitPartner] = []
    for pid in approved_partner_ids:
        part = partners.get(pid)
        if not part:
            continue
        names = [users.get(uid, "?") for uid in verdicts[pid]["yes"]]
        result.append(OutfitPartner(item=ItemOut.model_validate(part), approved_by=names))
    return result


def _verdict_pairs(
    db: Session, item_ids: set[int]
) -> tuple[set[frozenset[int]], set[frozenset[int]]]:
    """Return (rejected, approved) item-id pairs. A rejection by anyone wins.

    Only pairs where both items live in the given wardrobe are considered.
    """
    rejected: set[frozenset[int]] = set()
    approved: set[frozenset[int]] = set()
    for m in db.query(Match).all():
        if m.item_a_id not in item_ids or m.item_b_id not in item_ids:
            continue
        pair = frozenset((m.item_a_id, m.item_b_id))
        if m.verdict == "no":
            rejected.add(pair)
        elif m.verdict == "yes":
            approved.add(pair)
    approved -= rejected
    return rejected, approved


@router.get("/suggestions", response_model=list[OutfitSuggestion])
def suggestions(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Suggest whole outfits from the wardrobe using the colour knowledge base.

    Pairs that any wardrobe member rejected are never suggested; pairs that
    were already approved are boosted.
    """
    require_view(db, wardrobe_id, user)
    items = _wardrobe_items(db, wardrobe_id)
    if len(items) < 2:
        return []

    rejected, approved = _verdict_pairs(db, {it.id for it in items})
    good_pairs, bad_pairs = load_pairs(db)
    outfits = suggest_outfits(
        items, rejected, approved, limit=30, good_pairs=good_pairs, bad_pairs=bad_pairs
    )
    return [
        OutfitSuggestion(
            items=[ItemOut.model_validate(it) for it in o["items"]],
            score=o["score"],
            reason=o["reason"],
        )
        for o in outfits
    ]


@router.get("/suggestions/{item_id}", response_model=list[OutfitSuggestion])
def suggestions_for_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Automatic outfit suggestions that include one specific item, shown on
    that item's page below the manually approved combinations."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    require_view(db, item.wardrobe_id, user)
    items = _wardrobe_items(db, item.wardrobe_id)
    if len(items) < 2:
        return []

    rejected, approved = _verdict_pairs(db, {it.id for it in items})
    good_pairs, bad_pairs = load_pairs(db)
    outfits = suggest_outfits(
        items, rejected, approved, limit=12,
        good_pairs=good_pairs, bad_pairs=bad_pairs, must_include=item_id,
    )
    return [
        OutfitSuggestion(
            items=[ItemOut.model_validate(it) for it in o["items"]],
            score=o["score"],
            reason=o["reason"],
        )
        for o in outfits
    ]


@router.get("/stats")
def stats(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, wardrobe_id, user)
    items = _wardrobe_items(db, wardrobe_id)
    n = len(items)
    item_ids = {it.id for it in items}
    # Only count pairs that can share a season; the rest are never shown, so
    # including them would make the progress bar unable to reach 100%.
    total_pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            if seasons_compatible(items[i].season, items[j].season) and can_combine(
                items[i].category, items[j].category
            ):
                total_pairs += 1
    judged_by_me = len(_judged_pairs(db, user.id, item_ids))
    return {
        "item_count": n,
        "total_pairs": total_pairs,
        "judged_by_me": judged_by_me,
        "remaining_for_me": max(total_pairs - judged_by_me, 0),
    }
