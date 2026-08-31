from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import app_settings, audit
from ..access import ensure_wardrobe
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas import AuthConfig, PasswordChange, RegistrationIn, Token, UserOut
from ..security import create_access_token, hash_password, verify_password
from .photos import clear_photo_cookie, set_photo_cookie

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    response: Response,
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
    # <img> requests cannot carry the bearer token, so photos are authorised
    # by this cookie instead.
    set_photo_cookie(response, token)
    audit.record(db, "auth.login", f"{user.display_name} logde in", user=user)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/config", response_model=AuthConfig)
def auth_config(db: Session = Depends(get_db)):
    """What the login screen may offer. Readable without being logged in.

    The screen has to say *something* to someone without an account, and "vraag
    je beheerder om een uitnodiging" is only the right answer while the front
    door is actually shut — so it asks first.
    """
    return AuthConfig(self_registration=app_settings.self_registration_open(db))


@router.put("/config", response_model=AuthConfig)
def update_auth_config(
    body: AuthConfig,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Open or close self-registration. Beheerders only."""
    was = app_settings.self_registration_open(db)
    app_settings.set_bool(db, app_settings.SELF_REGISTRATION, body.self_registration)
    if was != body.self_registration:
        audit.record(
            db,
            "auth.registration_toggle",
            "Zelf registreren staat nu "
            + ("open — iedereen kan een account aanmaken" if body.self_registration
               else "dicht — alleen op uitnodiging"),
            user=admin,
        )
    return AuthConfig(self_registration=body.self_registration)


@router.post("/register", response_model=Token, status_code=201)
def register(
    body: RegistrationIn,
    response: Response,
    db: Session = Depends(get_db),
):
    """Create your own account — only while a beheerder leaves the door open.

    With the toggle off this answers 403 rather than 404: the endpoint exists,
    it is the installation that is closed, and saying so is what lets the login
    screen explain the difference instead of guessing.
    """
    if not app_settings.self_registration_open(db):
        raise HTTPException(
            status_code=403,
            detail="Zelf registreren staat uit — je hebt een uitnodiging nodig",
        )
    username = body.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Deze gebruikersnaam bestaat al")

    user = User(
        username=username,
        display_name=body.display_name.strip(),
        hashed_password=hash_password(body.password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_wardrobe(db, user)

    audit.record(
        db,
        "user.self_register",
        f"{user.display_name} (@{user.username}) maakte zelf een account aan",
        user=user,
        entity_type="user",
        entity_id=user.id,
    )
    token = create_access_token(user.id)
    set_photo_cookie(response, token)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    # The app calls this on every start, which is also where a session that
    # predates the photo cookie (or whose cookie has expired) gets one.
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        set_photo_cookie(response, header[7:].strip())
    return user


@router.post("/logout", status_code=204)
def logout():
    """Drop the photo cookie. The bearer token itself lives in the browser."""
    response = Response(status_code=204)
    clear_photo_cookie(response)
    return response


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
