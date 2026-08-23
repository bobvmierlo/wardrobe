"""Removing an account, and everything that hangs off it.

Deleting a row from ``users`` is the easy part; the hard part is that an
account is the root of a small tree — a wardrobe, its garments and photos,
every verdict the person cast, the kasten they were invited to, the links they
handed out. SQLite does not enforce the ``ondelete`` clauses the models declare
unless foreign keys are switched on, and even then SQLAlchemy would need to be
told about each dependency. Left to itself, ``db.delete(user)`` removes one row
and orphans the rest.

Orphans are not merely untidy. SQLite reuses a freed row id, so the next
account created takes the deleted account's id, and ``ensure_wardrobe`` then
hands it the deleted person's kast — clothes and all. That is the bug this
module exists to prevent, so removal happens here, explicitly, in one
transaction.

What survives on purpose: the audit trail. Its rows keep the actor's *name*
and lose only the id, so "wie heeft dit verwijderd?" stays answerable after the
account is gone.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .images import delete_files
from .logging_setup import get_logger
from .models import (
    AuditLog,
    Invitation,
    Item,
    Match,
    MatchSkip,
    User,
    Wardrobe,
    WardrobeMember,
)

log = get_logger("accounts")


def _drop_item_verdicts(db: Session, item_ids: list[int]) -> None:
    """Remove every verdict and postponement touching these garments.

    Not just the owner's: a shared kast collects verdicts from everyone, and
    all of them point at garments that are about to stop existing.
    """
    if not item_ids:
        return
    for model in (Match, MatchSkip):
        db.query(model).filter(
            model.item_a_id.in_(item_ids) | model.item_b_id.in_(item_ids)
        ).delete(synchronize_session=False)


def clear_wardrobe_items(db: Session, wardrobe: Wardrobe) -> int:
    """Empty a kast: its garments, their photos and every verdict on them.

    The kast itself, its members and its invitations stay. Used by a restore in
    "vervangen" mode, where the wardrobe survives but its contents are replaced.
    Returns how many garments were removed. Caller commits.
    """
    items = db.query(Item).filter(Item.wardrobe_id == wardrobe.id).all()
    _drop_item_verdicts(db, [it.id for it in items])
    for item in items:
        delete_files(item.photo_filename, item.thumb_filename)
    if items:
        db.query(Item).filter(Item.wardrobe_id == wardrobe.id).delete(
            synchronize_session=False
        )
    return len(items)


def purge_wardrobe(db: Session, wardrobe: Wardrobe) -> int:
    """Delete a wardrobe with its garments, photos, verdicts and sharing.

    Returns how many garments went with it. Caller commits.
    """
    removed = clear_wardrobe_items(db, wardrobe)
    db.query(WardrobeMember).filter(
        WardrobeMember.wardrobe_id == wardrobe.id
    ).delete(synchronize_session=False)
    db.query(Invitation).filter(Invitation.wardrobe_id == wardrobe.id).delete(
        synchronize_session=False
    )
    db.delete(wardrobe)
    return removed


def delete_account(db: Session, user: User, reassign_items_to: User) -> dict[str, int]:
    """Remove an account and everything belonging to it. Caller commits.

    Garments the person added to *someone else's* kast are kept and handed to
    ``reassign_items_to`` (the admin doing the deletion): those belong to the
    other kast, not to the departing account, and deleting them would quietly
    take away another household's clothes.

    Returns a small tally for the audit line.
    """
    user_id = user.id
    tally = {"wardrobes": 0, "items": 0, "verdicts": 0, "invitations": 0, "memberships": 0}

    # Their own kast, with everything in it.
    for wardrobe in db.query(Wardrobe).filter(Wardrobe.owner_id == user_id).all():
        tally["items"] += purge_wardrobe(db, wardrobe)
        tally["wardrobes"] += 1

    # Their verdicts elsewhere (in kasten that stay).
    tally["verdicts"] = db.query(Match).filter(Match.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(MatchSkip).filter(MatchSkip.user_id == user_id).delete(
        synchronize_session=False
    )

    # Their access to other people's kasten.
    tally["memberships"] = db.query(WardrobeMember).filter(
        WardrobeMember.user_id == user_id
    ).delete(synchronize_session=False)

    # Links they handed out go; links they *used* stay, with the trace removed.
    tally["invitations"] = db.query(Invitation).filter(
        Invitation.created_by_id == user_id
    ).delete(synchronize_session=False)
    db.query(Invitation).filter(Invitation.accepted_by_id == user_id).update(
        {Invitation.accepted_by_id: None}, synchronize_session=False
    )

    # Garments they added to a kast that is not theirs: keep the garment, move
    # the authorship, so the other household loses nothing.
    db.query(Item).filter(Item.created_by_id == user_id).update(
        {Item.created_by_id: reassign_items_to.id}, synchronize_session=False
    )

    # The audit trail keeps the name and loses the link.
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update(
        {AuditLog.user_id: None}, synchronize_session=False
    )

    db.delete(user)
    log.info(
        "Account %s (@%s) verwijderd: %s", user.display_name, user.username, tally
    )
    return tally
