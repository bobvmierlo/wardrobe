from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import app_settings, audit
from ..access import ensure_wardrobe
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..config import settings
from ..schemas import (
    AuthConfig,
    AuthConfigUpdate,
    PasswordChange,
    RegistrationIn,
    Token,
    UserOut,
)
from ..security import create_access_token, hash_password, verify_password
from ..throttle import client_key, login_throttle
from .photos import clear_photo_cookie, set_photo_cookie

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form.username.strip().lower()
    # Counted per account *and* per caller; see app.throttle for why both.
    keys = (
        f"user:{username}",
        client_key(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
        ),
    )
    wait = login_throttle.retry_after(*keys)
    if wait:
        audit.record(
            db,
            "auth.login_throttled",
            f"Inlogpoging voor '{username}' geweigerd: te veel mislukte pogingen",
            user_name=username,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Te veel mislukte inlogpogingen. Probeer het over {wait} seconden opnieuw.",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        login_throttle.record_failure(*keys)
        # Logged with the attempted name (never the password) so a beheerder
        # can tell a forgotten password from someone knocking on the door.
        audit.record(
            db,
            "auth.login_failed",
            f"Mislukte inlogpoging voor '{username}'",
            user_name=username,
        )
        raise HTTPException(status_code=401, detail="Onjuiste gebruikersnaam of wachtwoord")

    # A correct password forgives the typos that came before it.
    login_throttle.record_success(*keys)
    token = create_access_token(user.id, token_version=user.token_version)
    # <img> requests cannot carry the bearer token, so photos are authorised
    # by this cookie instead.
    set_photo_cookie(response, token, request)
    audit.record(db, "auth.login", f"{user.display_name} logde in", user=user)
    return Token(access_token=token, user=UserOut.model_validate(user))


def _auth_config(db: Session) -> AuthConfig:
    return AuthConfig(
        self_registration=app_settings.self_registration_open(db),
        oidc_enabled=settings.oidc_configured,
        oidc_label=settings.oidc_button_label if settings.oidc_configured else "",
        oidc_manages_admins=settings.oidc_configured
        and bool(settings.oidc_admin_group.strip()),
        local_login=settings.local_login,
        min_password_length=settings.min_password_length,
    )


@router.get("/config", response_model=AuthConfig)
def auth_config(db: Session = Depends(get_db)):
    """What the login screen may offer. Readable without being logged in.

    The screen has to say *something* to someone without an account, and "vraag
    je beheerder om een uitnodiging" is only the right answer while the front
    door is actually shut — so it asks first.
    """
    return _auth_config(db)


@router.put("/config", response_model=AuthConfig)
def update_auth_config(
    body: AuthConfigUpdate,
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
    return _auth_config(db)


@router.post("/register", response_model=Token, status_code=201)
def register(
    body: RegistrationIn,
    request: Request,
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
    token = create_access_token(user.id, token_version=user.token_version)
    set_photo_cookie(response, token, request)
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
        set_photo_cookie(response, header[7:].strip(), request)
    return user


@router.post("/logout", status_code=204)
def logout():
    """Drop the photo cookie. The bearer token itself lives in the browser."""
    response = Response(status_code=204)
    clear_photo_cookie(response)
    return response


@router.post("/change-password", response_model=Token)
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change your own password, knowing the current one.

    Two things this does beyond storing a new hash.

    It asks for the **current** password first. Without that, anyone who got
    hold of a session — a borrowed unlocked phone, a token read out of
    localStorage — could swap the password and keep the account for good. Asking
    turns that from permanent into temporary.

    And it **ends every other session**, by moving the account's token version
    past the one those tokens carry. A password change that leaves the old
    sessions running for another thirty days is not really a password change;
    it is what you do *because* you think someone else has one.

    An account that has no local password yet (it signs in through SSO) is
    setting a first one, so there is nothing to prove — it is logged as such.
    """
    had_password = user.has_password
    if had_password:
        if not body.current_password or not verify_password(
            body.current_password, user.hashed_password
        ):
            audit.record(
                db,
                "auth.password_change_failed",
                f"Mislukte poging om het wachtwoord van {user.display_name} te"
                " wijzigen: huidig wachtwoord onjuist",
                user=user,
                entity_type="user",
                entity_id=user.id,
            )
            raise HTTPException(
                status_code=403, detail="Je huidige wachtwoord is niet juist"
            )
        if body.current_password == body.new_password:
            raise HTTPException(
                status_code=400,
                detail="Het nieuwe wachtwoord is hetzelfde als het huidige",
            )

    user.hashed_password = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    db.refresh(user)
    audit.record(
        db,
        "auth.password_change",
        f"{user.display_name} wijzigde het eigen wachtwoord — andere sessies"
        " zijn uitgelogd"
        if had_password
        else f"{user.display_name} stelde een lokaal wachtwoord in"
        " (dit account logde alleen via SSO in)",
        user=user,
        entity_type="user",
        entity_id=user.id,
    )
    # The caller's own token died with the others, so hand them a fresh one:
    # changing your password should not log you out of the device you did it on.
    token = create_access_token(user.id, token_version=user.token_version)
    set_photo_cookie(response, token, request)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout-everywhere", response_model=Token)
def logout_everywhere(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """End every session on every device, and keep this one.

    The thing you reach for when a phone goes missing. Same mechanism as a
    password change, without having to change the password.
    """
    user.token_version += 1
    db.commit()
    db.refresh(user)
    audit.record(
        db,
        "auth.logout_everywhere",
        f"{user.display_name} logde alle andere apparaten uit",
        user=user,
        entity_type="user",
        entity_id=user.id,
    )
    token = create_access_token(user.id, token_version=user.token_version)
    set_photo_cookie(response, token, request)
    return Token(access_token=token, user=UserOut.model_validate(user))
