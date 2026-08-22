from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit
from ..access import require_view
from ..database import get_db
from ..deps import get_current_user
from ..matching import can_combine, is_cross_group, seasons_compatible
from ..models import Item, Match, MatchSkip, User, as_utc, utcnow
from ..routers.color_rules import load_pairs
from ..schemas import (
    ItemOut,
    JudgedPair,
    MatchCreate,
    OutfitPartner,
    OutfitSuggestion,
    PairOut,
    PairSkip,
    PairVote,
    SuggestionAccept,
)
from ..suggestions import all_pairs, is_combination, suggest_outfits

router = APIRouter(prefix="/api/matches", tags=["matches"])


def _ordered(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _wardrobe_items(db: Session, wardrobe_id: int) -> list[Item]:
    return db.query(Item).filter(Item.wardrobe_id == wardrobe_id).all()


def _judged_pairs(db: Session, user_id: int, item_ids: set[int]) -> set[frozenset[int]]:
    rows = db.query(Match.item_a_id, Match.item_b_id).filter(Match.user_id == user_id).all()
    return {frozenset((a, b)) for a, b in rows if a in item_ids and b in item_ids}


def _skipped_pairs(
    db: Session, user_id: int, item_ids: set[int]
) -> dict[frozenset[int], datetime]:
    """Pairs this user postponed, mapped to when they did so.

    The timestamp is what puts a skipped pair "achteraan in de rij": the
    longest-ago skip resurfaces first, and skipping again moves it back.
    """
    rows = (
        db.query(MatchSkip.item_a_id, MatchSkip.item_b_id, MatchSkip.created_at)
        .filter(MatchSkip.user_id == user_id)
        .all()
    )
    return {
        # Normalise: rows written in this session are timezone-aware, rows read
        # back from SQLite are naive, and the two cannot be compared.
        frozenset((a, b)): as_utc(when)
        for a, b, when in rows
        if a in item_ids and b in item_ids
    }


def _drop_skip(db: Session, user_id: int, a: int, b: int) -> None:
    """Forget a postponement — the pair has now been judged (or reset)."""
    db.query(MatchSkip).filter(
        MatchSkip.item_a_id == a,
        MatchSkip.item_b_id == b,
        MatchSkip.user_id == user_id,
    ).delete()


def _pair_items(db: Session, item_a_id: int, item_b_id: int, user: User) -> tuple[Item, Item]:
    """Load both items of a pair, checking they are combinable by this user."""
    a, b = _ordered(item_a_id, item_b_id)
    if a == b:
        raise HTTPException(
            status_code=400, detail="Een stuk kan niet met zichzelf gecombineerd worden"
        )
    item_a, item_b = db.get(Item, a), db.get(Item, b)
    if not item_a or not item_b:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    if item_a.wardrobe_id != item_b.wardrobe_id:
        raise HTTPException(status_code=400, detail="Stukken uit verschillende kasten")
    # A viewer may vote, so view access is enough here.
    require_view(db, item_a.wardrobe_id, user)
    return item_a, item_b


@router.get("/next", response_model=PairOut | None)
def next_pair(
    wardrobe_id: int,
    anchor_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the next pair for the current user to judge, within one wardrobe.

    Pass ``anchor_id`` to keep swiping candidates for one garment. Omit it to
    let the server pick the garment with the most work left. Pairs the user
    skipped come last, so everything unseen is offered before anything they
    already put off once.
    """
    require_view(db, wardrobe_id, user)
    items = _wardrobe_items(db, wardrobe_id)
    if len(items) < 2:
        return None
    by_id = {it.id: it for it in items}
    judged = _judged_pairs(db, user.id, set(by_id))
    skipped = _skipped_pairs(db, user.id, set(by_id))

    def candidates_for(anchor: Item) -> list[Item]:
        cands = [
            it for it in items
            if it.id != anchor.id
            and frozenset((anchor.id, it.id)) not in judged
            and seasons_compatible(anchor.season, it.season)
            and can_combine(anchor.category, it.category)
        ]
        # Never-seen pairs first (cross-group before same-group, newest first),
        # then the skipped ones in the order they were put off.
        def sort_key(it: Item):
            when = skipped.get(frozenset((anchor.id, it.id)))
            return (
                when is not None,
                when.timestamp() if when else 0.0,
                not is_cross_group(anchor.category, it.category),
                -it.id,
            )

        cands.sort(key=sort_key)
        return cands

    def is_skipped(anchor: Item, candidate: Item) -> bool:
        return frozenset((anchor.id, candidate.id)) in skipped

    def unskipped_count(anchor: Item, cands: list[Item]) -> int:
        return sum(1 for c in cands if not is_skipped(anchor, c))

    if anchor_id is not None:
        anchor = by_id.get(anchor_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Ankerstuk niet gevonden")
        cands = candidates_for(anchor)
        if not cands:
            return None
        return PairOut(
            anchor=ItemOut.model_validate(anchor),
            candidate=ItemOut.model_validate(cands[0]),
            skipped=is_skipped(anchor, cands[0]),
        )

    # No anchor: prefer the item with the most pairs the user has never seen,
    # and only fall back to anchors that hold nothing but skipped pairs.
    best_anchor = None
    best_cands: list[Item] = []
    best_key = (-1, -1)
    for anchor in items:
        cands = candidates_for(anchor)
        if not cands:
            continue
        key = (unskipped_count(anchor, cands), len(cands))
        if key > best_key:
            best_anchor, best_cands, best_key = anchor, cands, key
    if best_anchor is None or not best_cands:
        return None
    return PairOut(
        anchor=ItemOut.model_validate(best_anchor),
        candidate=ItemOut.model_validate(best_cands[0]),
        skipped=is_skipped(best_anchor, best_cands[0]),
    )


@router.post("", status_code=204)
def submit_verdict(
    body: MatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item_a, item_b = _pair_items(db, body.item_a_id, body.item_b_id, user)
    a, b = item_a.id, item_b.id

    existing = (
        db.query(Match)
        .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
        .first()
    )
    was = existing.verdict if existing else None
    if existing:
        existing.verdict = body.verdict
    else:
        db.add(Match(item_a_id=a, item_b_id=b, user_id=user.id, verdict=body.verdict))
    # Judging a pair settles it, so any earlier postponement is moot.
    _drop_skip(db, user.id, a, b)
    db.commit()

    said = "past bij elkaar" if body.verdict == "yes" else "past niet"
    changed = f" (was: {'past bij elkaar' if was == 'yes' else 'past niet'})" if was else ""
    audit.record(
        db,
        "match.verdict",
        f"{item_a.name} + {item_b.name}: {said}{changed}",
        user=user,
        wardrobe_id=item_a.wardrobe_id,
        entity_type="match",
        entity_id=a,
    )
    return Response(status_code=204)


@router.post("/skip", status_code=204)
def skip_pair(
    body: PairSkip,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Postpone a pair without judging it: it returns at the end of the queue."""
    item_a, item_b = _pair_items(db, body.item_a_id, body.item_b_id, user)
    a, b = item_a.id, item_b.id

    already_judged = (
        db.query(Match)
        .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
        .first()
    )
    if already_judged:
        raise HTTPException(
            status_code=409, detail="Dit paar is al beoordeeld; maak het eerst ongedaan"
        )

    skip = (
        db.query(MatchSkip)
        .filter(
            MatchSkip.item_a_id == a,
            MatchSkip.item_b_id == b,
            MatchSkip.user_id == user.id,
        )
        .first()
    )
    if skip:
        # Skipped again: move it behind everything else that was put off.
        skip.created_at = utcnow()
    else:
        db.add(MatchSkip(item_a_id=a, item_b_id=b, user_id=user.id))
    db.commit()

    audit.record(
        db,
        "match.skip",
        f"{item_a.name} + {item_b.name} overgeslagen",
        user=user,
        wardrobe_id=item_a.wardrobe_id,
        entity_type="match",
        entity_id=a,
    )
    return Response(status_code=204)


@router.get("/judged", response_model=list[JudgedPair])
def judged_pairs(
    wardrobe_id: int,
    verdict: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every pair the current user judged in this wardrobe, newest first.

    This is what the "ongedaan maken" list is built from: it shows the user's
    own verdict plus what the other members said, so it is clear whether
    undoing a mistake actually changes the outcome.
    """
    require_view(db, wardrobe_id, user)
    if verdict is not None and verdict not in {"yes", "no"}:
        raise HTTPException(status_code=400, detail="Ongeldig oordeel")

    items = {it.id: it for it in _wardrobe_items(db, wardrobe_id)}
    if not items:
        return []

    mine = (
        db.query(Match)
        .filter(
            Match.user_id == user.id,
            Match.item_a_id.in_(items),
            Match.item_b_id.in_(items),
        )
        .order_by(Match.updated_at.desc())
        .all()
    )
    if verdict:
        mine = [m for m in mine if m.verdict == verdict]
    if not mine:
        return []

    my_pairs = {(m.item_a_id, m.item_b_id) for m in mine}
    others = (
        db.query(Match)
        .filter(Match.item_a_id.in_(items), Match.item_b_id.in_(items))
        .all()
    )
    names = {u.id: u.display_name for u in db.query(User).all()}
    votes: dict[tuple[int, int], list[PairVote]] = {}
    for m in others:
        key = (m.item_a_id, m.item_b_id)
        if key not in my_pairs:
            continue
        votes.setdefault(key, []).append(
            PairVote(
                user_id=m.user_id,
                display_name=names.get(m.user_id, "?"),
                verdict=m.verdict,
            )
        )

    return [
        JudgedPair(
            item_a=ItemOut.model_validate(items[m.item_a_id]),
            item_b=ItemOut.model_validate(items[m.item_b_id]),
            my_verdict=m.verdict,
            votes=sorted(
                votes.get((m.item_a_id, m.item_b_id), []),
                key=lambda v: v.display_name.lower(),
            ),
            updated_at=m.updated_at,
        )
        for m in mine
    ]


@router.delete("/{item_a_id}/{item_b_id}", status_code=204)
def reset_pair(
    item_a_id: int,
    item_b_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Undo the current user's verdict for a pair, so it can be judged again.

    Used when someone approved or rejected a combination by accident: the pair
    goes straight back into the swipe queue.
    """
    a, b = _ordered(item_a_id, item_b_id)
    item_a, item_b = db.get(Item, a), db.get(Item, b)
    if item_a is not None:
        require_view(db, item_a.wardrobe_id, user)
    removed = (
        db.query(Match)
        .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
        .delete()
    )
    # An undone pair should come back as unseen, not as postponed.
    _drop_skip(db, user.id, a, b)
    db.commit()

    if removed:
        names = " + ".join(
            it.name for it in (item_a, item_b) if it is not None
        ) or f"{a} + {b}"
        audit.record(
            db,
            "match.undo",
            f"Beoordeling van {names} ongedaan gemaakt",
            user=user,
            wardrobe_id=item_a.wardrobe_id if item_a else None,
            entity_type="match",
            entity_id=a,
        )


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

    Outfits the household already decided on are left out: a pair anyone
    rejected is never suggested, and an outfit whose pairs are all approved is
    a combination already — it belongs under Outfits, not here.
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


@router.post("/suggestions/accept", status_code=204)
def accept_suggestion(
    body: SuggestionAccept,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Turn a suggested outfit into a real combination.

    Approving the outfit approves every pair inside it in one go, on the
    current user's behalf. Refused when the outfit is already a combination,
    or when any of its pairs was rejected before — a suggestion may never
    overrule a decision that was already made.
    """
    ids = list(dict.fromkeys(body.item_ids))
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Een combinatie heeft minstens 2 stukken")

    items = db.query(Item).filter(Item.id.in_(ids)).all()
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    wardrobe_ids = {it.wardrobe_id for it in items}
    if len(wardrobe_ids) > 1:
        raise HTTPException(status_code=400, detail="Stukken uit verschillende kasten")
    wardrobe_id = items[0].wardrobe_id
    # A viewer may vote, so view access is enough here.
    require_view(db, wardrobe_id, user)

    all_item_ids = {it.id for it in _wardrobe_items(db, wardrobe_id)}
    rejected, approved = _verdict_pairs(db, all_item_ids)
    pairs = all_pairs(items)
    if pairs & rejected:
        raise HTTPException(
            status_code=409, detail="Deze combinatie is eerder afgekeurd"
        )
    if is_combination(items, approved):
        raise HTTPException(
            status_code=409, detail="Deze combinatie bestaat al"
        )

    added = 0
    for pair in pairs:
        a, b = _ordered(*pair)
        existing = (
            db.query(Match)
            .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
            .first()
        )
        if existing:
            if existing.verdict != "yes":
                existing.verdict = "yes"
                added += 1
        else:
            db.add(Match(item_a_id=a, item_b_id=b, user_id=user.id, verdict="yes"))
            added += 1
        _drop_skip(db, user.id, a, b)
    db.commit()

    audit.record(
        db,
        "match.accept_suggestion",
        f"Suggestie {' + '.join(it.name for it in items)} als combinatie opgeslagen"
        f" ({added} {'paar' if added == 1 else 'paren'} goedgekeurd)",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="suggestion",
        entity_id=items[0].id,
    )
    return Response(status_code=204)


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
    skipped_by_me = len(_skipped_pairs(db, user.id, item_ids))
    return {
        "item_count": n,
        "total_pairs": total_pairs,
        "judged_by_me": judged_by_me,
        "skipped_by_me": skipped_by_me,
        "remaining_for_me": max(total_pairs - judged_by_me, 0),
    }
