"""Wardrobes ("kasten") and sharing.

Each user owns one wardrobe and can invite others to it as an editor (may
change garments) or a viewer (may only look and vote). Admins can reach every
wardrobe with full rights.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..access import (
    can_edit,
    can_manage,
    ensure_wardrobe,
    require_manage,
    require_view,
    role_for,
)
from ..database import get_db
from ..deps import get_current_user
from ..models import User, Wardrobe, WardrobeMember
from ..schemas import (
    MemberInvite,
    MemberRoleUpdate,
    UserOut,
    WardrobeMemberOut,
    WardrobeOut,
)

router = APIRouter(prefix="/api/wardrobes", tags=["wardrobes"])


def _member_count(db: Session, wardrobe_id: int) -> int:
    return (
        db.query(WardrobeMember)
        .filter(WardrobeMember.wardrobe_id == wardrobe_id)
        .count()
    )


def _to_out(db: Session, wardrobe: Wardrobe, role: str) -> WardrobeOut:
    return WardrobeOut(
        id=wardrobe.id,
        name=wardrobe.name,
        owner=UserOut.model_validate(wardrobe.owner),
        my_role=role,
        can_edit=can_edit(role),
        can_manage=can_manage(role),
        member_count=_member_count(db, wardrobe.id),
    )


@router.get("", response_model=list[WardrobeOut])
def list_wardrobes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every wardrobe the current user can open.

    That is their own kast, any kast they were invited to, and — for admins —
    all other kasten too. The user's own wardrobe always comes first.
    """
    own = ensure_wardrobe(db, user)

    if user.is_admin:
        candidates = db.query(Wardrobe).all()
    else:
        shared_ids = [
            m.wardrobe_id
            for m in db.query(WardrobeMember)
            .filter(WardrobeMember.user_id == user.id)
            .all()
        ]
        candidates = [own]
        if shared_ids:
            candidates += db.query(Wardrobe).filter(Wardrobe.id.in_(shared_ids)).all()

    result: list[WardrobeOut] = []
    for w in candidates:
        role = role_for(db, w, user)
        if role is None:
            continue
        result.append(_to_out(db, w, role))
    # Own kast first, then by owner display name.
    result.sort(key=lambda w: (w.id != own.id, w.owner.display_name.lower()))
    return result


@router.get("/{wardrobe_id}/members", response_model=list[WardrobeMemberOut])
def list_members(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Who this wardrobe is shared with. Any member may see the list."""
    require_view(db, wardrobe_id, user)
    members = (
        db.query(WardrobeMember)
        .filter(WardrobeMember.wardrobe_id == wardrobe_id)
        .all()
    )
    return [
        WardrobeMemberOut(user=UserOut.model_validate(m.user), role=m.role)
        for m in members
    ]


@router.post("/{wardrobe_id}/members", response_model=WardrobeMemberOut, status_code=201)
def invite_member(
    wardrobe_id: int,
    body: MemberInvite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invite another user to this wardrobe as an editor or viewer."""
    wardrobe, _ = require_manage(db, wardrobe_id, user)

    username = body.username.strip().lower()
    invitee = db.query(User).filter(User.username == username).first()
    if invitee is None:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    if invitee.id == wardrobe.owner_id:
        raise HTTPException(
            status_code=400, detail="De eigenaar heeft al volledige toegang"
        )

    member = (
        db.query(WardrobeMember)
        .filter(
            WardrobeMember.wardrobe_id == wardrobe_id,
            WardrobeMember.user_id == invitee.id,
        )
        .first()
    )
    if member:
        member.role = body.role  # re-inviting just updates the role
    else:
        member = WardrobeMember(
            wardrobe_id=wardrobe_id, user_id=invitee.id, role=body.role
        )
        db.add(member)
    db.commit()
    db.refresh(member)
    audit.record(
        db,
        "member.invite",
        f"{invitee.display_name} kreeg toegang tot '{wardrobe.name}' als {member.role}",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="member",
        entity_id=invitee.id,
    )
    return WardrobeMemberOut(user=UserOut.model_validate(invitee), role=member.role)


@router.patch(
    "/{wardrobe_id}/members/{user_id}", response_model=WardrobeMemberOut
)
def update_member(
    wardrobe_id: int,
    user_id: int,
    body: MemberRoleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change a member's role between editor and viewer."""
    require_manage(db, wardrobe_id, user)
    member = (
        db.query(WardrobeMember)
        .filter(
            WardrobeMember.wardrobe_id == wardrobe_id,
            WardrobeMember.user_id == user_id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Lid niet gevonden")
    member.role = body.role
    db.commit()
    db.refresh(member)
    audit.record(
        db,
        "member.update",
        f"{member.user.display_name} is nu {member.role} op deze kast",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="member",
        entity_id=user_id,
    )
    return WardrobeMemberOut(user=UserOut.model_validate(member.user), role=member.role)


@router.delete("/{wardrobe_id}/members/{user_id}", status_code=204)
def remove_member(
    wardrobe_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a user's access to this wardrobe."""
    require_manage(db, wardrobe_id, user)
    removed = db.get(User, user_id)
    db.query(WardrobeMember).filter(
        WardrobeMember.wardrobe_id == wardrobe_id,
        WardrobeMember.user_id == user_id,
    ).delete()
    db.commit()
    audit.record(
        db,
        "member.remove",
        f"Toegang van {removed.display_name if removed else user_id} tot deze kast ingetrokken",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="member",
        entity_id=user_id,
    )
