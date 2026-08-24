from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit
from ..access import require_view
from ..database import get_db
from ..deps import get_current_user
from ..matching import can_combine, is_cross_group, is_upper, seasons_compatible
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
    RejectedPartner,
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


def _pair_queue(
    db: Session,
    wardrobe_id: int,
    user: User,
    anchor_id: int | None,
    limit: int,
) -> list[PairOut]:
    """The pairs this user still has to judge, best first.

    One ordering serves both endpoints: the swipe screen asks for the head of
    this queue, and the app asks for a stretch of it to carry offline. Because
    both come from here, what someone swipes through without a connection is
    exactly what the server would have handed them one at a time.
    """
    require_view(db, wardrobe_id, user)
    items = _wardrobe_items(db, wardrobe_id)
    if len(items) < 2:
        return []
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

    def as_pair(anchor: Item, candidate: Item) -> PairOut:
        """One pair, always the same way round: bovenstuk first, onderstuk second.

        Which of the two drove the queue is a detail of *finding* the pair; the
        screen shows the bovenstuk on the left and the onderstuk on the right,
        every single time. Anchoring on a broek therefore puts that broek on the
        right — the garment stays the same, only the side is fixed. Because the
        order is decided here rather than by which item happened to be the
        anchor, the same two garments can never come by twice with the sides
        swapped. ``can_combine`` guarantees exactly one of the two is upper wear.
        """
        top, bottom = (
            (anchor, candidate) if is_upper(anchor.category) else (candidate, anchor)
        )
        return PairOut(
            anchor=ItemOut.model_validate(top),
            candidate=ItemOut.model_validate(bottom),
            skipped=is_skipped(anchor, candidate),
        )

    if anchor_id is not None:
        anchor = by_id.get(anchor_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Ankerstuk niet gevonden")
        ranked = [(anchor, candidates_for(anchor))]
    else:
        # No anchor: work through the garments with the most unseen pairs first,
        # falling back to anchors that hold nothing but skipped pairs.
        scored = []
        for anchor in items:
            cands = candidates_for(anchor)
            if cands:
                scored.append(((unskipped_count(anchor, cands), len(cands)), anchor, cands))
        scored.sort(key=lambda row: row[0], reverse=True)
        ranked = [(anchor, cands) for _key, anchor, cands in scored]

    queue: list[PairOut] = []
    seen: set[frozenset[int]] = set()
    for anchor, cands in ranked:
        for candidate in cands:
            # The same two garments rank under both of them; offer them once.
            key = frozenset((anchor.id, candidate.id))
            if key in seen:
                continue
            seen.add(key)
            queue.append(as_pair(anchor, candidate))
            if len(queue) >= limit:
                return queue
    return queue


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
    queue = _pair_queue(db, wardrobe_id, user, anchor_id, limit=1)
    return queue[0] if queue else None


@router.get("/next/queue", response_model=list[PairOut])
def next_pairs(
    wardrobe_id: int,
    anchor_id: int | None = None,
    limit: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A stretch of the queue at once, so swiping survives a lost connection.

    The app keeps these in hand and works through them locally; verdicts given
    without a connection are queued by the service worker and replayed later.
    Capped because the point is a pocketful of pairs, not the whole wardrobe.
    """
    return _pair_queue(db, wardrobe_id, user, anchor_id, limit=max(1, min(limit, 100)))


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


def _partner_verdicts(
    db: Session, item: Item, user: User
) -> tuple[dict[int, dict[str, set[int]]], dict[int, Item]]:
    """Every verdict cast on this garment, grouped per partner garment.

    Returns ``{partner_id: {"yes": {user_id}, "no": {user_id}}}`` along with the
    partner items themselves. Only partners inside the same wardrobe count.
    """
    require_view(db, item.wardrobe_id, user)
    partners = {it.id: it for it in _wardrobe_items(db, item.wardrobe_id)}
    rows = (
        db.query(Match)
        .filter((Match.item_a_id == item.id) | (Match.item_b_id == item.id))
        .all()
    )
    verdicts: dict[int, dict[str, set[int]]] = {}
    for m in rows:
        partner_id = m.item_b_id if m.item_a_id == item.id else m.item_a_id
        if partner_id not in partners:
            continue
        verdicts.setdefault(partner_id, {"yes": set(), "no": set()})
        verdicts[partner_id][m.verdict].add(m.user_id)
    return verdicts, partners


def _names(db: Session, user_ids: set[int]) -> list[str]:
    """Display names for a set of voters, alphabetically so the order is stable."""
    if not user_ids:
        return []
    rows = db.query(User).filter(User.id.in_(user_ids)).all()
    known = {u.id: u.display_name for u in rows}
    return sorted((known.get(uid, "?") for uid in user_ids), key=str.lower)


def _get_item(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    return item


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
    item = _get_item(db, item_id)
    verdicts, partners = _partner_verdicts(db, item, user)

    result: list[OutfitPartner] = []
    for pid, v in verdicts.items():
        if not v["yes"] or v["no"]:
            continue
        part = partners.get(pid)
        if not part:
            continue
        result.append(
            OutfitPartner(
                item=ItemOut.model_validate(part), approved_by=_names(db, v["yes"])
            )
        )
    return result


@router.get("/rejected/{item_id}", response_model=list[RejectedPartner])
def rejected_for(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Items judged *not* to go with the given item, and who said so.

    Deliberately its own endpoint rather than a flag on the approved list: a
    rejected pair is not an outfit and must never leak into the Outfits screen.
    It belongs on the garment's own page, where "waarom staat die combinatie
    er niet bij?" is the question being asked.
    """
    item = _get_item(db, item_id)
    verdicts, partners = _partner_verdicts(db, item, user)

    result: list[RejectedPartner] = []
    for pid, v in verdicts.items():
        if not v["no"]:
            continue
        part = partners.get(pid)
        if not part:
            continue
        result.append(
            RejectedPartner(
                item=ItemOut.model_validate(part),
                rejected_by=_names(db, v["no"]),
                approved_by=_names(db, v["yes"]),
                rejected_by_me=user.id in v["no"],
            )
        )
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


@router.post("/suggestions/undo", status_code=204)
def undo_suggestion(
    body: SuggestionAccept,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Take back a whole adopted outfit: every pair in it goes back to unjudged.

    The mirror image of accepting a suggestion. Doing this pair by pair from
    the frontend meant one request per pair — fifteen of them for a six-piece
    outfit — and one audit line each, which buried what was actually one act.
    """
    ids = list(dict.fromkeys(body.item_ids))
    items = db.query(Item).filter(Item.id.in_(ids)).all()
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="Kledingstuk niet gevonden")
    wardrobe_ids = {it.wardrobe_id for it in items}
    if len(wardrobe_ids) > 1:
        raise HTTPException(status_code=400, detail="Stukken uit verschillende kasten")
    wardrobe_id = items[0].wardrobe_id
    require_view(db, wardrobe_id, user)

    removed = 0
    for pair in all_pairs(items):
        a, b = _ordered(*pair)
        removed += (
            db.query(Match)
            .filter(Match.item_a_id == a, Match.item_b_id == b, Match.user_id == user.id)
            .delete()
        )
        # An undone pair should come back as unseen, not as postponed.
        _drop_skip(db, user.id, a, b)
    db.commit()

    if removed:
        audit.record(
            db,
            "match.undo_suggestion",
            f"Combinatie {' + '.join(it.name for it in items)} ongedaan gemaakt"
            f" ({removed} {'paar' if removed == 1 else 'paren'} teruggezet)",
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
