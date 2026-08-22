from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import PasswordChange, Token, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form.username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        # Logged with the attempted name (never the password) so a beheerder
        # can tell a forgotten password from someone knocking on the door.
        audit.record(
            db,
            "auth.login_failed",
            f"Mislukte inlogpoging voor '{username}'",
            user_name=username,
        )
        raise HTTPException(status_code=401, detail="Onjuiste gebruikersnaam of wachtwoord")
    token = create_access_token(user.id)
    audit.record(db, "auth.login", f"{user.display_name} logde in", user=user)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    audit.record(
        db,
        "auth.password_change",
        f"{user.display_name} wijzigde het eigen wachtwoord",
        user=user,
        entity_type="user",
        entity_id=user.id,
    )
