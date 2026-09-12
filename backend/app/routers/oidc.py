"""The three HTTP steps of a federated login.

``/login`` sends the browser to the provider, ``/callback`` catches it coming
back, and ``/exchange`` is how the single-page app collects the token that came
out of it. The reasoning behind that last hop — rather than putting the token in
the redirect — is in :class:`app.oidc.HandoffStore`.

Everything here is unauthenticated by necessity: the whole point is that nobody
is signed in yet. What guards it is the signed state cookie, PKCE, and the
signature on the provider's ID token.
"""

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi import Depends
from sqlalchemy.orm import Session

from .. import audit, oidc
from ..config import settings
from ..database import get_db
from ..logging_setup import get_logger
from ..models import Invitation, User, Wardrobe
from ..schemas import OidcExchange, Token, UserOut
from ..security import create_access_token
from .invitations import _redeem as redeem_invitation
from .invitations import _usable as usable_invitation
from .photos import set_photo_cookie

router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])
log = get_logger("oidc")

#: Carries the PKCE verifier and nonce across the round trip. Scoped to this
#: router's path so it travels with the callback and nothing else.
STATE_COOKIE = "wardrobe_oidc_state"
COOKIE_PATH = "/api/auth/oidc"


def _require_configured() -> None:
    if not settings.oidc_configured:
        raise HTTPException(
            status_code=404,
            detail="Inloggen via SSO is niet ingesteld op deze Kledingkast",
        )


def _base_url(request: Request) -> str:
    """Where a browser reaches this app, for building the redirect URI.

    ``WARDROBE_PUBLIC_URL`` wins when it is set, and setting it is the advice:
    the redirect URI has to match what is registered at the provider character
    for character, and deriving it from proxy headers makes that depend on a
    reverse proxy's configuration.
    """
    if settings.public_url.strip():
        return settings.public_url.strip().rstrip("/")
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _redirect_uri(request: Request) -> str:
    return f"{_base_url(request)}/api/auth/oidc/callback"


def _safe_next(path: str | None) -> str:
    """Only ever redirect inside this app.

    ``next`` arrives from a query string, so "//evil.example" and
    "https://evil.example" both have to be refused — an open redirect on a
    login route is how a convincing phishing page gets its address bar right.
    """
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    return path


def _error_redirect(message: str) -> RedirectResponse:
    response = RedirectResponse(
        url=f"/login#oidc_error={quote(message, safe='')}", status_code=303
    )
    response.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/login")
def oidc_login(
    request: Request,
    next: str = Query("/"),
    invite: str | None = Query(None),
):
    """Send the browser to the provider to sign in."""
    _require_configured()
    try:
        started = oidc.begin(
            _redirect_uri(request),
            next_path=_safe_next(next),
            invite=(invite or "").strip() or None,
        )
    except oidc.OidcError as exc:
        return _error_redirect(str(exc))

    response = RedirectResponse(url=started.authorization_url, status_code=303)
    response.set_cookie(
        STATE_COOKIE,
        started.state_cookie,
        max_age=oidc.STATE_TTL_SECONDS,
        httponly=True,
        # "lax" and not "strict": the provider's redirect is a cross-site
        # navigation, and a strict cookie would not be sent with it.
        samesite="lax",
        path=COOKIE_PATH,
        secure=_base_url(request).startswith("https://"),
    )
    return response


def _resolve_user(
    db: Session, result: oidc.Completed
) -> tuple[User, bool, str | None]:
    """Turn verified claims into an account.

    Returns the user, whether it was just created, and an override for where to
    send the browser afterwards (used when an invitation turned out not to be
    redeemable, so the invitation page itself can explain why).
    """
    oidc.check_allowed(result.groups)

    user = oidc.find_user(db, result.claims)
    if user is None:
        user = oidc.link_existing(db, result.claims)
    if user is not None:
        oidc.refresh_profile(db, user, result.claims)
        return user, False, None

    # Nobody here yet. An invitation is what authorises creating an account
    # while the front door is shut, so check that it is real before making one.
    invitation: Invitation | None = None
    if result.invite:
        try:
            invitation = usable_invitation(db, result.invite)
        except HTTPException as exc:
            log.warning(
                "SSO-login met een uitnodiging die niet (meer) bruikbaar is: %s",
                exc.detail,
            )
            invitation = None

    if invitation is None and not settings.oidc_auto_create:
        raise oidc.OidcError(
            "Je bent wel ingelogd bij de inlogdienst, maar je hebt nog geen"
            " account in deze Kledingkast. Vraag de beheerder om een"
            " uitnodigingslink."
        )

    user = oidc.create_user(db, result.claims)
    return user, True, None


def _apply_invitation(
    db: Session, user: User, token: str | None, *, created: bool
) -> str | None:
    """Redeem the invitation the login came through, if there is one.

    Never fatal. The person has proved who they are; a link that was already
    used is a thing to explain, not a reason to refuse them their own wardrobe.
    Returns a path to send them to instead of the default, when there is
    something for them to read.
    """
    if not token:
        return None
    try:
        invitation = usable_invitation(db, token)
    except HTTPException as exc:
        log.info("Uitnodiging bij SSO-login niet verzilverd: %s", exc.detail)
        # Let the invitation page say what is wrong with it, in its own words.
        return f"/invite/{token}"

    if invitation.wardrobe_id is None:
        if not created:
            # An account link only makes a login, and this person has one.
            log.info("Accountuitnodiging genegeerd: %s had al een account", user.username)
            return None
    else:
        wardrobe = db.get(Wardrobe, invitation.wardrobe_id)
        if wardrobe is None:
            return f"/invite/{token}"
        if wardrobe.owner_id == user.id:
            return None  # their own kast; nothing to grant

    redeem_invitation(db, invitation, user)
    audit.record(
        db,
        "invitation.accept",
        f"{user.display_name} accepteerde de uitnodiging via SSO"
        + (
            f" voor '{invitation.wardrobe.name}' (rol: {invitation.role})"
            if invitation.wardrobe_id is not None and invitation.wardrobe
            else " voor een nieuw account"
        ),
        user=user,
        wardrobe_id=invitation.wardrobe_id,
        entity_type="invitation",
        entity_id=invitation.id,
        commit=False,
    )
    return None


@router.get("/callback")
def oidc_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    state_cookie: str | None = Cookie(None, alias=STATE_COOKIE),
    db: Session = Depends(get_db),
):
    """Catch the browser coming back from the provider and finish the login."""
    _require_configured()

    if error:
        # The provider refused, e.g. the person cancelled or is not assigned to
        # the application. Its own description is the useful part.
        log.warning("De inlogdienst gaf een fout terug: %s (%s)", error, error_description)
        return _error_redirect(
            error_description or f"De inlogdienst weigerde de aanmelding ({error})."
        )
    if not code or not state_cookie:
        return _error_redirect(
            "Deze inlogpoging is verlopen of hoort niet bij deze browser."
            " Probeer het opnieuw."
        )

    try:
        result = oidc.complete(state_cookie, state or "", code)
        user, created, override = _resolve_user(db, result)
        db.flush()
        oidc.sync_admin(
            db, user, result.groups, claim_missing=result.groups_claim_missing
        )
        invite_override = _apply_invitation(db, user, result.invite, created=created)
        db.commit()
    except oidc.OidcError as exc:
        db.rollback()
        audit.record(
            db,
            "auth.oidc_failed",
            f"Mislukte SSO-login: {exc}",
            user_name="via SSO",
        )
        return _error_redirect(str(exc))
    except Exception:
        db.rollback()
        log.exception("Onverwachte fout tijdens een SSO-login")
        return _error_redirect(
            "Er ging iets mis bij het inloggen via SSO. Kijk in het logboek van"
            " de server voor de details."
        )

    db.refresh(user)
    audit.record(
        db,
        "auth.oidc_login",
        f"{user.display_name} logde in via SSO"
        + (" (nieuw account)" if created else ""),
        user=user,
    )

    destination = override or invite_override or result.next_path
    handoff = oidc.handoffs.issue(user.id)
    response = RedirectResponse(
        url=f"{destination}#{urlencode({'oidc': handoff})}", status_code=303
    )
    response.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    return response


@router.post("/exchange", response_model=Token)
def oidc_exchange(
    body: OidcExchange,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Trade the one-time code from the redirect for an ordinary app token.

    The answer is byte-for-byte the shape ``/api/auth/login`` returns, so the
    app stores it the same way and knows nothing about how it was obtained.
    """
    _require_configured()
    user_id = oidc.handoffs.redeem(body.code.strip())
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="Deze inlogpoging is verlopen. Probeer opnieuw in te loggen.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Dit account bestaat niet meer")

    token = create_access_token(user.id, token_version=user.token_version)
    set_photo_cookie(response, token, request)
    return Token(access_token=token, user=UserOut.model_validate(user))
