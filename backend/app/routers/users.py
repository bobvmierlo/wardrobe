from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..access import ensure_wardrobe
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from ..security import hash_password

    username = body.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Gebruikersnaam bestaat al")
    user = User(
        username=username,
        display_name=body.display_name.strip(),
        hashed_password=hash_password(body.password),
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Give the new user their own wardrobe right away.
    ensure_wardrobe(db, user)
    audit.record(
        db,
        "user.create",
        f"Account '{user.display_name}' (@{user.username}) aangemaakt"
        f"{' als beheerder' if user.is_admin else ''}",
        user=admin,
        entity_type="user",
        entity_id=user.id,
    )
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Grant or revoke the beheerder (admin) role for a user."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    # Don't let the last remaining admin demote themselves and lock everyone out.
    if user.is_admin and not body.is_admin:
        admins = db.query(User).filter(User.is_admin.is_(True)).count()
        if admins <= 1:
            raise HTTPException(status_code=400, detail="Er moet minstens één beheerder blijven")
    user.is_admin = body.is_admin
    db.commit()
    db.refresh(user)
    audit.record(
        db,
        "user.update",
        f"{user.display_name} is nu {'beheerder' if user.is_admin else 'gewone gebruiker'}",
        user=admin,
        entity_type="user",
        entity_id=user.id,
    )
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Je kunt je eigen account niet verwijderen")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    name, uname = user.display_name, user.username
    db.delete(user)
    db.commit()
    audit.record(
        db,
        "user.delete",
        f"Account '{name}' (@{uname}) verwijderd",
        user=admin,
        entity_type="user",
        entity_id=user_id,
    )
