"""Wardrobe access control.

Every user owns one wardrobe. Others gain access when the owner invites them:

* **editor** — may add, edit and delete garments, and vote on combinations.
* **viewer** — may only look and vote on combinations.

An **admin** user can reach every wardrobe (even ones they were never invited
to) with full rights, while still being an ordinary user with their own kast.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import ROLE_EDITOR, ROLE_VIEWER, Item, User, Wardrobe, WardrobeMember

# Effective roles, most to least privileged. "owner" and "admin" both imply
# full (editor-level) rights; they are kept distinct so the UI can label them.
ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"

_EDIT_ROLES = {ROLE_ADMIN, ROLE_OWNER, ROLE_EDITOR}


def ensure_wardrobe(db: Session, user: User) -> Wardrobe:
    """Return the user's own wardrobe, creating it on first access."""
    wardrobe = db.query(Wardrobe).filter(Wardrobe.owner_id == user.id).first()
    if wardrobe is None:
        wardrobe = Wardrobe(owner_id=user.id, name=f"Kast van {user.display_name}")
        db.add(wardrobe)
        db.commit()
        db.refresh(wardrobe)
    return wardrobe


def accessible_wardrobe_ids(db: Session, user: User) -> list[int]:
    """Ids of every wardrobe the user may open: their own, any shared with them,
    and — for an admin — all of them."""
    if user.is_admin:
        return [w_id for (w_id,) in db.query(Wardrobe.id).all()]
    ids = {
        w_id
        for (w_id,) in db.query(Wardrobe.id).filter(Wardrobe.owner_id == user.id).all()
    }
    ids.update(
        w_id
        for (w_id,) in db.query(WardrobeMember.wardrobe_id)
        .filter(WardrobeMember.user_id == user.id)
        .all()
    )
    return sorted(ids)


def role_for(db: Session, wardrobe: Wardrobe, user: User) -> str | None:
    """The user's effective role on ``wardrobe``, or ``None`` for no access."""
    if wardrobe.owner_id == user.id:
        return ROLE_OWNER
    if user.is_admin:
        return ROLE_ADMIN
    member = (
        db.query(WardrobeMember)
        .filter(
            WardrobeMember.wardrobe_id == wardrobe.id,
            WardrobeMember.user_id == user.id,
        )
        .first()
    )
    return member.role if member else None


def can_edit(role: str | None) -> bool:
    return role in _EDIT_ROLES


def can_manage(role: str | None) -> bool:
    """Only the owner (or an admin) may invite/remove members."""
    return role in {ROLE_ADMIN, ROLE_OWNER}


def get_wardrobe(db: Session, wardrobe_id: int) -> Wardrobe:
    wardrobe = db.get(Wardrobe, wardrobe_id)
    if wardrobe is None:
        raise HTTPException(status_code=404, detail="Kast niet gevonden")
    return wardrobe


def require_view(db: Session, wardrobe_id: int, user: User) -> tuple[Wardrobe, str]:
    """Ensure the user may look inside the wardrobe (also enough to vote)."""
    wardrobe = get_wardrobe(db, wardrobe_id)
    role = role_for(db, wardrobe, user)
    if role is None:
        raise HTTPException(status_code=403, detail="Geen toegang tot deze kast")
    return wardrobe, role


def require_edit(db: Session, wardrobe_id: int, user: User) -> tuple[Wardrobe, str]:
    """Ensure the user may change garments in the wardrobe."""
    wardrobe, role = require_view(db, wardrobe_id, user)
    if not can_edit(role):
        raise HTTPException(
            status_code=403, detail="Alleen-lezen toegang: je mag deze kast niet bewerken"
        )
    return wardrobe, role


def require_manage(db: Session, wardrobe_id: int, user: User) -> tuple[Wardrobe, str]:
    """Ensure the user may manage who the wardrobe is shared with."""
    wardrobe, role = require_view(db, wardrobe_id, user)
    if not can_manage(role):
        raise HTTPException(
            status_code=403, detail="Alleen de eigenaar kan deze kast delen"
        )
    return wardrobe, role


def item_wardrobe(db: Session, item: Item) -> Wardrobe:
    """The wardrobe a garment belongs to (never null in practice)."""
    return get_wardrobe(db, item.wardrobe_id)


__all__ = [
    "ROLE_ADMIN",
    "ROLE_OWNER",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
    "ensure_wardrobe",
    "accessible_wardrobe_ids",
    "role_for",
    "can_edit",
    "can_manage",
    "get_wardrobe",
    "require_view",
    "require_edit",
    "require_manage",
    "item_wardrobe",
]
