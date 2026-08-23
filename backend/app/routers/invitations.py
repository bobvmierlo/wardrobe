"""Invitation links.

Sharing a kast used to require the other person to already have an account,
which they could only get from an admin. An invitation link closes that gap
without opening the front door: the owner creates a link, sends it however they
like, and the holder either signs in and accepts it, or registers an account
*through that link*.

Self-service registration stays disabled — :func:`register_via_invitation` is
the only path to a new account besides an admin creating one, and it refuses
anything but a valid, unused, unexpired token.
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit
from ..access import ROLE_OWNER, ensure_wardrobe, require_manage, role_for
from ..database import get_db
from ..deps import get_current_user
from ..models import Invitation, User, Wardrobe, WardrobeMember, utcnow
from ..schemas import (
    InvitationCreate,
    InvitationInfo,
    InvitationOut,
    InvitationRegister,
    Token,
    UserOut,
)
from ..security import create_access_token, hash_password
from .photos import set_photo_cookie

router = APIRouter(prefix="/api/invitations", tags=["invitations"])
# Creating and listing links belongs to a wardrobe, so those live under the
# wardrobe path; redeeming one only needs the token.
wardrobe_router = APIRouter(prefix="/api/wardrobes", tags=["invitations"])


def _to_out(inv: Invitation) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        token=inv.token,
        path=f"/invite/{inv.token}",
        role=inv.role,
        label=inv.label,
        status=inv.status,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        accepted_by=UserOut.model_validate(inv.accepted_by) if inv.accepted_by else None,
    )


def _usable(db: Session, token: str) -> Invitation:
    """Load an invitation that may still be redeemed, or explain why not.

    Every failure answers with 404/410 and no detail about the wardrobe, so a
    guessed token reveals nothing.
    """
    inv = db.query(Invitation).filter(Invitation.token == token).first()
    if inv is None:
        raise HTTPException(status_code=404, detail="Deze uitnodiging bestaat niet (meer)")
    status = inv.status
    if status == "revoked":
        raise HTTPException(status_code=410, detail="Deze uitnodiging is ingetrokken")
    if status == "accepted":
        raise HTTPException(status_code=410, detail="Deze uitnodiging is al gebruikt")
    if status == "expired":
        raise HTTPException(status_code=410, detail="Deze uitnodiging is verlopen")
    return inv


def _redeem(db: Session, inv: Invitation, user: User) -> None:
    """Grant the invited role and mark the link used. Caller commits."""
    member = (
        db.query(WardrobeMember)
        .filter(
            WardrobeMember.wardrobe_id == inv.wardrobe_id,
            WardrobeMember.user_id == user.id,
        )
        .first()
    )
    if member:
        member.role = inv.role
    else:
        db.add(
            WardrobeMember(
                wardrobe_id=inv.wardrobe_id, user_id=user.id, role=inv.role
            )
        )
    inv.accepted_at = utcnow()
    inv.accepted_by_id = user.id


@wardrobe_router.post(
    "/{wardrobe_id}/invitations", response_model=InvitationOut, status_code=201
)
def create_invitation(
    wardrobe_id: int,
    body: InvitationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a one-time link that grants access to this wardrobe."""
    wardrobe, _role = require_manage(db, wardrobe_id, user)
    inv = Invitation(
        token=secrets.token_urlsafe(32),
        wardrobe_id=wardrobe_id,
        role=body.role,
        label=(body.label or "").strip() or None,
        created_by_id=user.id,
        expires_at=(
            utcnow() + timedelta(days=body.expires_days)
            if body.expires_days is not None
            else None
        ),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    audit.record(
        db,
        "invitation.create",
        f"Uitnodigingslink gemaakt voor {inv.label or 'onbekende ontvanger'}"
        f" (rol: {inv.role}) op '{wardrobe.name}'",
        user=user,
        wardrobe_id=wardrobe_id,
        entity_type="invitation",
        entity_id=inv.id,
    )
    return _to_out(inv)


@wardrobe_router.get("/{wardrobe_id}/invitations", response_model=list[InvitationOut])
def list_invitations(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every link ever made for this wardrobe, newest first."""
    require_manage(db, wardrobe_id, user)
    rows = (
        db.query(Invitation)
        .filter(Invitation.wardrobe_id == wardrobe_id)
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return [_to_out(inv) for inv in rows]


@router.delete("/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Withdraw a link. Already-accepted invitations keep their history."""
    inv = db.get(Invitation, invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Uitnodiging niet gevonden")
    require_manage(db, inv.wardrobe_id, user)
    if inv.revoked_at is None:
        inv.revoked_at = utcnow()
        db.commit()
        audit.record(
            db,
            "invitation.revoke",
            f"Uitnodigingslink voor {inv.label or 'onbekende ontvanger'} ingetrokken",
            user=user,
            wardrobe_id=inv.wardrobe_id,
            entity_type="invitation",
            entity_id=inv.id,
        )


@router.get("/{token}", response_model=InvitationInfo)
def invitation_info(token: str, db: Session = Depends(get_db)):
    """What the link says, for the not-yet-logged-in visitor who opened it.

    Public on purpose — the token *is* the credential — but it gives away
    nothing beyond the kast's name, its owner and the offered role.
    """
    inv = _usable(db, token)
    wardrobe = db.get(Wardrobe, inv.wardrobe_id)
    if wardrobe is None:
        raise HTTPException(status_code=404, detail="Deze uitnodiging bestaat niet (meer)")
    return InvitationInfo(
        wardrobe_name=wardrobe.name,
        owner_name=wardrobe.owner.display_name,
        role=inv.role,
        label=inv.label,
        status=inv.status,
        expires_at=inv.expires_at,
    )


@router.post("/{token}/accept", status_code=204)
def accept_invitation(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Redeem a link as the signed-in user."""
    inv = _usable(db, token)
    wardrobe = db.get(Wardrobe, inv.wardrobe_id)
    if wardrobe is None:
        raise HTTPException(status_code=404, detail="Deze uitnodiging bestaat niet (meer)")
    if role_for(db, wardrobe, user) == ROLE_OWNER:
        raise HTTPException(
            status_code=400, detail="Dit is je eigen kast — je hebt al volledige toegang"
        )
    _redeem(db, inv, user)
    db.commit()

    audit.record(
        db,
        "invitation.accept",
        f"{user.display_name} accepteerde de uitnodiging voor '{wardrobe.name}'"
        f" (rol: {inv.role})",
        user=user,
        wardrobe_id=inv.wardrobe_id,
        entity_type="invitation",
        entity_id=inv.id,
    )


@router.post("/{token}/register", response_model=Token, status_code=201)
def register_via_invitation(
    token: str,
    body: InvitationRegister,
    response: Response,
    db: Session = Depends(get_db),
):
    """Create an account *through* an invitation link and redeem it.

    The only self-service way to an account: without a valid token there is no
    registration endpoint at all. The new user is signed in straight away, so
    they land in the shared kast instead of on a login screen.
    """
    inv = _usable(db, token)
    wardrobe = db.get(Wardrobe, inv.wardrobe_id)
    if wardrobe is None:
        raise HTTPException(status_code=404, detail="Deze uitnodiging bestaat niet (meer)")

    username = body.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=409,
            detail="Deze gebruikersnaam bestaat al — log in en accepteer de uitnodiging",
        )

    user = User(
        username=username,
        display_name=body.display_name.strip(),
        hashed_password=hash_password(body.password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Every user owns a kast of their own, invited or not.
    ensure_wardrobe(db, user)

    _redeem(db, inv, user)
    db.commit()

    audit.record(
        db,
        "user.register",
        f"{user.display_name} (@{user.username}) registreerde via de uitnodiging"
        f" voor '{wardrobe.name}' (rol: {inv.role})",
        user=user,
        wardrobe_id=inv.wardrobe_id,
        entity_type="user",
        entity_id=user.id,
    )
    token_str = create_access_token(user.id)
    # Same as a normal login: the browser needs the photo cookie too.
    set_photo_cookie(response, token_str)
    return Token(access_token=token_str, user=UserOut.model_validate(user))
