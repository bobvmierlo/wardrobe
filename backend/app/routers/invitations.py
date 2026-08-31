"""Invitation links.

Two kinds of link, redeemed through the same page:

* a **kast invitation**, made by the owner of a kast, which grants access to
  that kast — the holder signs in and accepts it, or registers an account
  *through that link* and lands in the kast straight away;
* an **account invitation**, made by a beheerder, which shares no kast at all
  and only lets the holder create a login of their own (with, as always, a kast
  of their own).

Both exist because the front door is shut by default: unless a beheerder opens
self-registration (see :mod:`app.app_settings`), a valid, unused, unexpired
token is the only self-service way to an account.
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit
from ..access import ROLE_OWNER, ensure_wardrobe, require_manage, role_for
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Invitation, User, Wardrobe, WardrobeMember, utcnow
from ..schemas import (
    AccountInvitationCreate,
    InvitationCreate,
    InvitationInfo,
    InvitationOut,
    RegistrationIn,
    Token,
    UserOut,
)
from ..security import create_access_token, hash_password
from .photos import set_photo_cookie

router = APIRouter(prefix="/api/invitations", tags=["invitations"])
# Creating and listing kast links belongs to a wardrobe, so those live under
# the wardrobe path; redeeming one only needs the token.
wardrobe_router = APIRouter(prefix="/api/wardrobes", tags=["invitations"])


def _to_out(inv: Invitation) -> InvitationOut:
    account = inv.wardrobe_id is None
    return InvitationOut(
        id=inv.id,
        token=inv.token,
        kind=inv.kind,
        wardrobe_name=None if account else (inv.wardrobe.name if inv.wardrobe else None),
        path=f"/invite/{inv.token}",
        role=None if account else inv.role,
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
    """Grant the invited role and mark the link used. Caller commits.

    An account invitation has no kast to grant anything on, so for that one
    "redeeming" is only the marking.
    """
    if inv.wardrobe_id is None:
        inv.accepted_at = utcnow()
        inv.accepted_by_id = user.id
        return
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


def _wardrobe_of(db: Session, inv: Invitation) -> Wardrobe:
    """The kast a link grants access to, or 404 if it has since been deleted."""
    wardrobe = db.get(Wardrobe, inv.wardrobe_id)
    if wardrobe is None:
        raise HTTPException(status_code=404, detail="Deze uitnodiging bestaat niet (meer)")
    return wardrobe


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


# NOTE: the two account routes below must stay above ``GET /{token}`` — a
# literal path only wins from a path parameter when it is declared first, and
# "account" is a perfectly valid token as far as the router is concerned.
@router.post("/account", response_model=InvitationOut, status_code=201)
def create_account_invitation(
    body: AccountInvitationCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a one-time link to a brand-new account. Beheerders only.

    Unlike a kast link this shares nothing: the holder picks their own name,
    username and password and ends up with an ordinary account and their own
    empty kast. It is how you let someone in while self-registration stays
    closed.
    """
    inv = Invitation(
        token=secrets.token_urlsafe(32),
        wardrobe_id=None,
        label=(body.label or "").strip() or None,
        created_by_id=admin.id,
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
        "invitation.create_account",
        f"Accountuitnodiging gemaakt voor {inv.label or 'onbekende ontvanger'}",
        user=admin,
        entity_type="invitation",
        entity_id=inv.id,
    )
    return _to_out(inv)


@router.get("/account", response_model=list[InvitationOut])
def list_account_invitations(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Every account link ever handed out, newest first. Beheerders only."""
    rows = (
        db.query(Invitation)
        .filter(Invitation.wardrobe_id.is_(None))
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
    if inv.wardrobe_id is None:
        # An account link has no kast, so no owner either: only a beheerder
        # can take it back.
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Alleen voor beheerders")
    else:
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
    if inv.wardrobe_id is None:
        return InvitationInfo(
            kind="account",
            label=inv.label,
            status=inv.status,
            expires_at=inv.expires_at,
        )
    wardrobe = _wardrobe_of(db, inv)
    return InvitationInfo(
        kind="wardrobe",
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
    if inv.wardrobe_id is None:
        # Nothing to accept: an account link only creates a login, and this
        # person already has one. Say so instead of quietly burning the link.
        raise HTTPException(
            status_code=400,
            detail="Deze uitnodiging is bedoeld om een nieuw account mee aan te maken —"
            " je hebt er al één",
        )
    wardrobe = _wardrobe_of(db, inv)
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
    body: RegistrationIn,
    response: Response,
    db: Session = Depends(get_db),
):
    """Create an account *through* an invitation link and redeem it.

    Works for both kinds of link, and the newcomer is signed in straight away
    either way: with a kast link they land in the shared kast, with an account
    link in their own.
    """
    inv = _usable(db, token)
    wardrobe = None if inv.wardrobe_id is None else _wardrobe_of(db, inv)

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
        f"{user.display_name} (@{user.username}) registreerde via een uitnodiging"
        + (
            f" voor '{wardrobe.name}' (rol: {inv.role})"
            if wardrobe is not None
            else " voor een nieuw account"
        ),
        user=user,
        wardrobe_id=inv.wardrobe_id,
        entity_type="user",
        entity_id=user.id,
    )
    token_str = create_access_token(user.id)
    # Same as a normal login: the browser needs the photo cookie too.
    set_photo_cookie(response, token_str)
    return Token(access_token=token_str, user=UserOut.model_validate(user))
