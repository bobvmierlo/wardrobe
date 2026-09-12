"""Federated login through an OpenID Connect provider.

The app keeps its own accounts and its own bearer tokens; this module only adds
a second way of *proving who you are*. A successful round trip ends exactly
where a password login ends — a ``User`` row and a token minted by
:mod:`app.security` — so every screen, every access check and the offline
queue stay unaware that SSO exists at all.

What it does, in order:

1. :func:`begin` builds the authorisation URL (authorization code + PKCE) and a
   signed, short-lived state blob for the browser to carry back.
2. :func:`complete` verifies that blob, swaps the code for tokens, validates the
   ID token against the provider's published keys, and reads the claims.
3. :func:`resolve_user` turns those claims into an account, and
   :func:`sync_admin` applies the group → beheerder mapping.

Three decisions worth knowing about:

* **An account is recognised by ``sub``, never by e-mail or username.** Both of
  those are things a provider lets people edit; ``sub`` is the one claim
  promised to be stable for the life of the account. Matching on anything else
  means a rename at the provider can walk someone into a stranger's wardrobe.
* **Local passwords keep working.** There is no setting that turns the password
  endpoint off, because the provider being down, misconfigured or mid-upgrade
  must never be the reason nobody can reach their own clothes.
* **Nothing is fetched from the provider at startup.** Discovery and key
  material are looked up lazily and cached, so an unreachable provider costs
  one failed login rather than a container that will not boot.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.orm import Session

from . import audit
from .access import ensure_wardrobe
from .config import settings
from .logging_setup import get_logger
from .models import User
from .security import UNUSABLE_PASSWORD

log = get_logger("oidc")

#: Signature algorithms accepted for an ID token. Asymmetric only: "HS256"
#: would let anyone holding the client secret mint their own identities, and
#: "none" is not a signature at all.
ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256"]

#: How long the browser has to come back from the provider with a code.
STATE_TTL_SECONDS = 600

#: How long a finished login waits to be picked up by the app (see
#: :class:`HandoffStore`). Short, but long enough for a slow phone to load the
#: page that collects it.
HANDOFF_TTL_SECONDS = 120

#: Discovery is cached this long. Long enough to cost nothing, short enough
#: that rotating an endpoint does not need a container restart.
DISCOVERY_TTL_SECONDS = 3600

#: The signing keys are cached this long, and re-fetched straight away when a
#: token names a key we have not seen — that is what makes key rotation a
#: non-event. The floor stops an unknown kid from becoming a way to make the
#: app hammer the provider.
JWKS_TTL_SECONDS = 3600
JWKS_MIN_REFETCH_SECONDS = 60

HTTP_TIMEOUT = 10.0


#: Sent on every call to the provider. Identifiable on purpose: a reverse proxy
#: or WAF in front of an identity provider is free to refuse an anonymous
#: client, and "Kledingkast" in the access log is what lets an operator allow it
#: rather than guess. PyJWT's own JWKS client used to do these fetches with
#: urllib's default "Python-urllib/3.x", which is exactly the kind of thing such
#: a filter blocks — see :func:`_fetch_jwks`.
USER_AGENT = "Kledingkast/OIDC (+https://github.com/bobvmierlo/wardrobe)"


def _client() -> httpx.Client:
    """The HTTP client used for every call to the provider.

    *Every* call: discovery, the token exchange, userinfo **and** the signing
    keys. They used to not all come through here, and that cost an afternoon —
    see :func:`_fetch_jwks`.

    A function rather than an inline constructor so the tests can stand up a
    fake provider without reaching into anything global.
    """
    return httpx.Client(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


class OidcError(Exception):
    """Something went wrong in the round trip.

    The message is Dutch and shown to the person trying to sign in, so it says
    what they can do about it and never leaks claim values or tokens. Anything
    worth more detail goes to the log instead.
    """


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------

@dataclass
class _Discovery:
    document: dict[str, Any]
    fetched_at: float


_discovery: _Discovery | None = None


@dataclass
class _KeySet:
    keys: jwt.PyJWKSet
    fetched_at: float


_keys: _KeySet | None = None


def _fetch_discovery() -> _Discovery:
    url = f"{settings.oidc_issuer_url}/.well-known/openid-configuration"
    try:
        with _client() as client:
            response = client.get(url)
            response.raise_for_status()
            document = response.json()
    except Exception as exc:  # network, TLS, JSON — all the same to the caller
        log.error("Kan de SSO-configuratie niet ophalen van %s: %s", url, exc)
        raise OidcError(
            "De inlogdienst is niet bereikbaar. Probeer het later nog eens of"
            " log in met je gebruikersnaam."
        ) from exc

    for required in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not document.get(required):
            log.error("SSO-configuratie mist '%s' (%s)", required, url)
            raise OidcError("De inlogdienst gaf een onvolledige configuratie terug.")

    log.info(
        "SSO-configuratie geladen van %s (issuer: %s)", url, document["issuer"]
    )
    return _Discovery(document=document, fetched_at=time.monotonic())


def discovery() -> _Discovery:
    """The provider's metadata, fetched on first use and cached."""
    global _discovery
    if (
        _discovery is None
        or time.monotonic() - _discovery.fetched_at > DISCOVERY_TTL_SECONDS
    ):
        _discovery = _fetch_discovery()
    return _discovery


def reset_cache() -> None:
    """Forget the cached metadata and keys. Used by the tests."""
    global _discovery, _keys
    _discovery = None
    _keys = None


# ---------------------------------------------------------------------------
# Signing keys
# ---------------------------------------------------------------------------

def _fetch_jwks() -> jwt.PyJWKSet:
    """Fetch the provider's public keys, through the same client as everything else.

    This used to be PyJWT's ``PyJWKClient``, which does its own networking with
    ``urllib.request.urlopen``. That meant the one call that decides whether a
    login succeeds went out over a different HTTP stack than the other three:
    different timeout, different error text, and — the part that actually bit —
    urllib's default ``User-Agent: Python-urllib/3.x``, which the reverse
    proxies and WAFs people put in front of an identity provider routinely
    answer with 403. Discovery would load fine and the login would then fail
    claiming the ID token was invalid, which sent you to check the issuer and
    client id: both of them innocent.

    So the keys come through :func:`_client` like everything else, and a failure
    here says *keys* rather than *token*.
    """
    url = discovery().document["jwks_uri"]
    try:
        with _client() as client:
            response = client.get(url)
            response.raise_for_status()
            document = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        log.error(
            "Kon de sleutels van de inlogdienst niet ophalen van %s: HTTP %s",
            url,
            status,
        )
        raise OidcError(
            f"De sleutels van de inlogdienst zijn niet op te halen (foutcode {status})."
            " Het adres is wel bereikbaar, dus dit zit meestal in een"
            " reverse-proxy of firewall vóór je provider die dit verzoek"
            " tegenhoudt — níet in de issuer-URL of de client-id."
        ) from exc
    except Exception as exc:
        log.error("Kon de sleutels van de inlogdienst niet ophalen van %s: %s", url, exc)
        raise OidcError(
            "De sleutels van de inlogdienst zijn niet op te halen. Probeer het"
            " later nog eens of log in met je gebruikersnaam."
        ) from exc

    try:
        key_set = jwt.PyJWKSet.from_dict(document)
    except jwt.PyJWKSetError as exc:
        # Authentik with no Signing Key on the provider publishes an empty set
        # and signs with HS256 instead. That is a provider setting, and saying
        # so beats "the token is invalid".
        log.error("De inlogdienst publiceerde geen bruikbare sleutels op %s: %s", url, exc)
        raise OidcError(
            "De inlogdienst publiceert geen ondertekeningssleutels. Stel bij de"
            " toepassing van je provider een 'Signing Key' in (zonder die sleutel"
            " ondertekent bijvoorbeeld Authentik met HS256, en dat accepteert deze"
            " app niet)."
        ) from exc

    log.info(
        "Sleutels van de inlogdienst geladen van %s (%d sleutel(s))",
        url,
        len(key_set.keys),
    )
    return key_set


def _key_set(*, force: bool = False) -> jwt.PyJWKSet:
    """The provider's key set, cached. ``force`` re-fetches it now."""
    global _keys
    stale = _keys is None or time.monotonic() - _keys.fetched_at > JWKS_TTL_SECONDS
    if force or stale:
        if (
            force
            and _keys is not None
            and time.monotonic() - _keys.fetched_at < JWKS_MIN_REFETCH_SECONDS
        ):
            # A token naming an unknown kid must not become a way to make the
            # app hammer the provider on demand.
            return _keys.keys
        _keys = _KeySet(keys=_fetch_jwks(), fetched_at=time.monotonic())
    return _keys.keys


def _signing_key(id_token: str):
    """The key the provider signed this token with.

    Looked up by ``kid``; an unknown one means the provider has rotated its
    keys since we cached them, so the set is fetched once more before giving up.
    A token with no ``kid`` at all is matched against a single published key,
    which is what providers that publish exactly one key tend to send.
    """
    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
    except jwt.PyJWTError as exc:
        raise OidcError("Het identiteitsbewijs van de inlogdienst is onleesbaar.") from exc

    for attempt in (False, True):
        keys = _key_set(force=attempt)
        if kid is None:
            if len(keys.keys) == 1:
                return keys.keys[0]
        else:
            try:
                return keys[kid]
            except KeyError:
                pass
        if attempt:
            break
    log.error(
        "De inlogdienst ondertekende met een onbekende sleutel (kid=%s);"
        " gepubliceerd zijn: %s",
        kid,
        [k.key_id for k in _key_set().keys],
    )
    raise OidcError(
        "Het identiteitsbewijs is ondertekend met een sleutel die de inlogdienst"
        " niet publiceert. Is de ondertekeningssleutel net gewisseld, probeer het"
        " dan opnieuw."
    )


# ---------------------------------------------------------------------------
# State: what the browser carries to the provider and back
# ---------------------------------------------------------------------------

def _state_token(payload: dict[str, Any]) -> str:
    return jwt.encode(
        {**payload, "exp": int(time.time()) + STATE_TTL_SECONDS},
        settings.secret_key,
        algorithm="HS256",
    )


def _read_state(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise OidcError(
            "Deze inlogpoging is verlopen of hoort niet bij deze browser."
            " Probeer het opnieuw."
        ) from exc


@dataclass
class Begin:
    """Where to send the browser, and the cookie that must come back with it."""

    authorization_url: str
    state_cookie: str


def begin(redirect_uri: str, *, next_path: str = "/", invite: str | None = None) -> Begin:
    """Start a login: build the provider URL and the state to carry along.

    The verifier and nonce live in a signed cookie rather than in server
    memory, so a restart mid-login is merely a retry and nothing has to be
    shared between workers.
    """
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)

    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id.strip(),
        "redirect_uri": redirect_uri,
        "scope": " ".join(settings.oidc_scope_list),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    endpoint = discovery().document["authorization_endpoint"]
    separator = "&" if "?" in endpoint else "?"
    return Begin(
        authorization_url=f"{endpoint}{separator}{urlencode(params)}",
        state_cookie=_state_token(
            {
                "st": state,
                "cv": verifier,
                "nn": nonce,
                "nx": next_path,
                "inv": invite,
                "ru": redirect_uri,
            }
        ),
    )


@dataclass
class Completed:
    """The outcome of a verified round trip."""

    claims: dict[str, Any]
    groups: list[str] = field(default_factory=list)
    next_path: str = "/"
    invite: str | None = None
    #: True when the groups claim was nowhere to be found. Not an error on its
    #: own — it only matters when a mapping is configured — but the single most
    #: common reason an admin mapping "does not work", so it is surfaced rather
    #: than guessed at.
    groups_claim_missing: bool = False


def _exchange_code(token_endpoint: str, code: str, verifier: str, redirect_uri: str) -> dict:
    """Swap the authorisation code for tokens.

    Providers disagree about where the client secret goes: the spec's default
    is HTTP Basic, Authentik and several others expect it in the form body, and
    a mismatch shows up only as a flat "invalid_client". Rather than make that
    a setting nobody can debug, try one and fall back to the other.
    """
    client_id = settings.oidc_client_id.strip()
    client_secret = settings.oidc_client_secret.strip()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "client_id": client_id,
    }
    supported = discovery().document.get("token_endpoint_auth_methods_supported") or []
    # The spec's default when the provider says nothing is client_secret_basic.
    basic_first = not supported or "client_secret_basic" in supported
    attempts = ["basic", "post"] if basic_first else ["post", "basic"]

    last_error = ""
    with _client() as client:
        for method in attempts:
            if method == "basic":
                response = client.post(
                    token_endpoint, data=body, auth=(client_id, client_secret)
                )
            else:
                response = client.post(
                    token_endpoint, data={**body, "client_secret": client_secret}
                )
            if response.status_code < 400:
                if method != attempts[0]:
                    log.info(
                        "Tokenaanvraag geslaagd met client_secret_%s; de provider"
                        " accepteerde client_secret_%s niet.",
                        method,
                        attempts[0],
                    )
                return response.json()
            last_error = f"{response.status_code} {response.text[:200]}"
            log.debug("Tokenaanvraag met client_secret_%s faalde: %s", method, last_error)

    log.error("Tokenaanvraag bij de inlogdienst mislukt: %s", last_error)
    raise OidcError(
        "De inlogdienst weigerde deze aanmelding. Controleer de client-id en"
        " het client-secret van deze toepassing."
    )


def _userinfo(endpoint: str, access_token: str) -> dict[str, Any]:
    try:
        with _client() as client:
            response = client.get(
                endpoint, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        # Not fatal: the ID token already proved who this is, and userinfo is
        # only consulted for claims that were not in it.
        log.warning("Kon de userinfo van de inlogdienst niet ophalen: %s", exc)
        return {}


def complete(state_cookie: str, state_param: str, code: str) -> Completed:
    """Verify the callback and return the claims it proves."""
    state = _read_state(state_cookie)
    if not state_param or not secrets.compare_digest(
        str(state.get("st", "")), state_param
    ):
        log.warning("SSO-callback met een state die niet klopt; genegeerd.")
        raise OidcError(
            "Deze inlogpoging hoort niet bij deze browser. Probeer het opnieuw."
        )

    document = discovery().document
    tokens = _exchange_code(
        document["token_endpoint"], code, str(state["cv"]), str(state["ru"])
    )
    id_token = tokens.get("id_token")
    if not id_token:
        log.error("De inlogdienst gaf geen id_token terug; is de scope 'openid' toegestaan?")
        raise OidcError(
            "De inlogdienst gaf geen identiteitsbewijs terug. Controleer of de"
            " scope 'openid' is toegestaan voor deze toepassing."
        )

    advertised = document.get("id_token_signing_alg_values_supported") or []
    algorithms = [alg for alg in advertised if alg in ALLOWED_ALGORITHMS]
    if advertised and not algorithms:
        # Every algorithm the provider offers is one we refuse. In practice this
        # is a provider with no signing key, falling back to HS256 — a setting,
        # not a mystery, so name it.
        log.error(
            "De inlogdienst ondertekent alleen met %s; deze app accepteert"
            " alleen asymmetrische ondertekening (%s).",
            ", ".join(advertised),
            ", ".join(ALLOWED_ALGORITHMS),
        )
        raise OidcError(
            f"De inlogdienst ondertekent met {', '.join(advertised)}. Deze app"
            " accepteert alleen asymmetrische ondertekening (RS256 en"
            " vergelijkbaar): stel bij de toepassing van je provider een"
            " 'Signing Key' in."
        )
    algorithms = algorithms or ALLOWED_ALGORITHMS

    # Fetching the keys and verifying the token are separate failures with
    # separate causes, so they get separate messages. Lumping them together is
    # what once reported a blocked JWKS request as "controleer de issuer-URL".
    signing_key = _signing_key(id_token)
    try:
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=algorithms,
            audience=settings.oidc_client_id.strip(),
            issuer=document["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        log.error("Het identiteitsbewijs van de inlogdienst is ongeldig: %s", exc)
        raise OidcError(
            "Het identiteitsbewijs van de inlogdienst is niet geldig. Controleer"
            " de issuer-URL en de client-id."
        ) from exc

    # PyJWT validates everything the spec can check generically; the nonce is
    # ours to match, and it is what stops a replayed authorisation response.
    if not secrets.compare_digest(str(claims.get("nonce", "")), str(state["nn"])):
        log.warning("SSO-callback met een nonce die niet klopt; genegeerd.")
        raise OidcError("Deze inlogpoging is al gebruikt. Probeer het opnieuw.")

    if not str(claims.get("sub", "")).strip():
        raise OidcError("De inlogdienst gaf geen gebruikers-id (sub) terug.")

    # Groups are usually in the ID token, but whether a provider puts scope
    # claims there or only behind userinfo is a per-install setting — so look
    # in both before concluding the claim is absent.
    groups, found = _read_groups(claims)
    if not found and document.get("userinfo_endpoint") and tokens.get("access_token"):
        extra = _userinfo(document["userinfo_endpoint"], tokens["access_token"])
        if extra:
            claims = {**extra, **claims}
            groups, found = _read_groups(extra)

    return Completed(
        claims=claims,
        groups=groups,
        next_path=str(state.get("nx") or "/"),
        invite=state.get("inv") or None,
        groups_claim_missing=not found,
    )


def end_session_url(post_logout_redirect: str) -> str | None:
    """The provider's logout URL, when it publishes one and we are asked to use it."""
    if not settings.oidc_logout_redirect:
        return None
    endpoint = discovery().document.get("end_session_endpoint")
    if not endpoint:
        return None
    params = urlencode(
        {
            "client_id": settings.oidc_client_id.strip(),
            "post_logout_redirect_uri": post_logout_redirect,
        }
    )
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{params}"


# ---------------------------------------------------------------------------
# Claims → groups
# ---------------------------------------------------------------------------

def _claim_at(claims: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Read a claim by dotted path, e.g. "realm_access.roles" for Keycloak."""
    current: Any = claims
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _read_groups(claims: dict[str, Any]) -> tuple[list[str], bool]:
    """Normalise whatever the groups claim holds into a list of names.

    Providers are not consistent here: a list of strings (Authentik, Authelia,
    Keycloak), a single string, or a list of objects with a name. All three
    arrive as a plain list of strings. The second return value says whether the
    claim was present at all — absent and empty mean very different things when
    someone is debugging a mapping that does not fire.
    """
    raw, present = _claim_at(claims, settings.oidc_groups_claim)
    if not present or raw is None:
        return [], False
    if isinstance(raw, str):
        return [g.strip() for g in raw.replace(",", " ").split() if g.strip()], True
    if isinstance(raw, (list, tuple)):
        names: list[str] = []
        for entry in raw:
            if isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("id")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        return names, True
    log.warning(
        "De claim '%s' is een %s; verwacht een lijst met groepsnamen.",
        settings.oidc_groups_claim,
        type(raw).__name__,
    )
    return [], True


def has_group(groups: list[str], wanted: str) -> bool:
    """Case-insensitive membership test.

    Case-insensitive on purpose: group names are typed twice — once in the
    provider, once in a compose file — and "Kledingkast-Admins" not matching
    "kledingkast-admins" is a support question, not a security boundary.
    """
    target = wanted.strip().lower()
    return any(g.strip().lower() == target for g in groups)


# ---------------------------------------------------------------------------
# Claims → account
# ---------------------------------------------------------------------------

def _username_from(claims: dict[str, Any]) -> str:
    """A username for a brand-new account, within the app's own rules."""
    candidate = ""
    for key in ("preferred_username", "nickname", "email", "name"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            candidate = value.strip()
            break
    candidate = candidate.split("@")[0].strip().lower()
    cleaned = "".join(ch for ch in candidate if ch.isalnum() or ch in "._-")
    if len(cleaned) < 2:
        # Nothing usable in the claims; the sub is at least unique.
        cleaned = f"sso-{hashlib.sha256(str(claims['sub']).encode()).hexdigest()[:8]}"
    return cleaned[:50]


def _unique_username(db: Session, base: str) -> str:
    if db.query(User).filter(User.username == base).first() is None:
        return base
    for suffix in range(2, 100):
        candidate = f"{base[: 50 - len(str(suffix)) - 1]}-{suffix}"
        if db.query(User).filter(User.username == candidate).first() is None:
            return candidate
    raise OidcError("Kon geen vrije gebruikersnaam bepalen voor dit account.")


def _display_name_from(claims: dict[str, Any], fallback: str) -> str:
    for key in ("name", "preferred_username", "nickname", "email"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:100]
    return fallback


def check_allowed(groups: list[str]) -> None:
    """Refuse the login outright when a group allow-list is configured."""
    allowed = settings.oidc_allowed_group_list
    if not allowed:
        return
    if not any(has_group(groups, g) for g in allowed):
        raise OidcError(
            "Je account mag deze Kledingkast niet gebruiken. Vraag de beheerder"
            " om je aan de juiste groep toe te voegen."
        )


def _last_admin(db: Session, user: User) -> bool:
    """True when demoting this user would leave the installation without one."""
    return (
        user.is_admin
        and db.query(User).filter(User.is_admin.is_(True)).count() <= 1
    )


def sync_admin(db: Session, user: User, groups: list[str], *, claim_missing: bool) -> None:
    """Apply the group → beheerder mapping. Caller commits.

    With a mapping configured the provider is the authority on every login:
    in the group means beheerder, out of it means an ordinary user. That is the
    whole point — revoking the role in one place has to be enough.

    Two things it will not do. It never touches a local account, so the
    bootstrap beheerder stays reachable when the provider is not; and it never
    removes the last beheerder in the installation, because a renamed group
    should cost someone a role, not cost everyone the settings screen.
    """
    wanted_group = settings.oidc_admin_group.strip()
    if not wanted_group:
        return
    if not user.is_federated:
        return

    if claim_missing:
        # Silence here would read exactly like "you are not in the group".
        log.warning(
            "De claim '%s' zat niet in het identiteitsbewijs en niet in de"
            " userinfo van de inlogdienst. De beheerdersrol van %s blijft"
            " daardoor ongewijzigd. Voeg de groepen-scope toe aan de"
            " toepassing bij je provider.",
            settings.oidc_groups_claim,
            user.username,
        )
        audit.record(
            db,
            "auth.oidc_groups_missing",
            f"SSO-login van {user.display_name} bevatte geen"
            f" '{settings.oidc_groups_claim}'-claim — beheerdersrol niet"
            " gewijzigd. Controleer de groepen-scope bij je provider.",
            user=user,
            entity_type="user",
            entity_id=user.id,
            commit=False,
        )
        return

    should_be_admin = has_group(groups, wanted_group)
    if should_be_admin == user.is_admin:
        return

    if not should_be_admin and _last_admin(db, user):
        log.warning(
            "%s is niet (meer) lid van '%s', maar is de laatste beheerder —"
            " de rol blijft staan om de installatie niet onbeheerbaar te maken.",
            user.username,
            wanted_group,
        )
        audit.record(
            db,
            "auth.oidc_admin_kept",
            f"{user.display_name} zit niet in '{wanted_group}', maar is de"
            " laatste beheerder — beheerdersrol behouden",
            user=user,
            entity_type="user",
            entity_id=user.id,
            commit=False,
        )
        return

    user.is_admin = should_be_admin
    log.info(
        "%s is via SSO %s op basis van groep '%s'",
        user.username,
        "beheerder geworden" if should_be_admin else "gewone gebruiker geworden",
        wanted_group,
    )
    audit.record(
        db,
        "auth.oidc_admin_sync",
        f"{user.display_name} is via SSO "
        + (
            f"beheerder geworden (lid van '{wanted_group}')"
            if should_be_admin
            else f"gewone gebruiker geworden (geen lid van '{wanted_group}')"
        ),
        user=user,
        entity_type="user",
        entity_id=user.id,
        commit=False,
    )


def find_user(db: Session, claims: dict[str, Any]) -> User | None:
    """The account this ``sub`` already belongs to, if any."""
    return (
        db.query(User)
        .filter(User.oidc_subject == str(claims["sub"]))
        .first()
    )


def link_existing(db: Session, claims: dict[str, Any]) -> User | None:
    """Adopt a local account whose username matches. Caller commits.

    Only when the operator asked for it. It is how an installation that
    predates SSO hands its existing accounts over without anyone losing their
    wardrobe — and it is off by default because it trusts the provider not to
    let people choose their own ``preferred_username``.
    """
    if not settings.oidc_link_by_username:
        return None
    username = (claims.get("preferred_username") or "").strip().lower()
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None or user.oidc_subject is not None:
        return None
    user.oidc_subject = str(claims["sub"])
    user.auth_provider = "oidc"
    log.info("Bestaand account '%s' gekoppeld aan SSO op gebruikersnaam", username)
    audit.record(
        db,
        "auth.oidc_link",
        f"Account '{user.display_name}' (@{user.username}) is gekoppeld aan SSO"
        " op basis van de gebruikersnaam",
        user=user,
        entity_type="user",
        entity_id=user.id,
        commit=False,
    )
    return user


def create_user(db: Session, claims: dict[str, Any]) -> User:
    """Provision a fresh account from the claims. Caller commits.

    It gets no password at all: :data:`app.security.UNUSABLE_PASSWORD` can
    never be matched, so the only way into this account is the provider — until
    a beheerder or the person themselves sets a local password on purpose.
    """
    username = _unique_username(db, _username_from(claims))
    user = User(
        username=username,
        display_name=_display_name_from(claims, username),
        hashed_password=UNUSABLE_PASSWORD,
        is_admin=False,
        auth_provider="oidc",
        oidc_subject=str(claims["sub"]),
    )
    db.add(user)
    db.flush()
    ensure_wardrobe(db, user)
    log.info("Nieuw account '%s' aangemaakt via SSO", username)
    return user


def refresh_profile(db: Session, user: User, claims: dict[str, Any]) -> None:
    """Keep the display name in step with the provider. Caller commits.

    The *username* is deliberately left alone: it is what the audit trail and
    the kast name were written with, and renaming it afterwards would make the
    log harder to read for no gain.
    """
    name = _display_name_from(claims, user.display_name)
    if name and name != user.display_name:
        user.display_name = name


# ---------------------------------------------------------------------------
# Handing the finished login to the app
# ---------------------------------------------------------------------------

class HandoffStore:
    """One-time codes that trade a finished SSO login for an app token.

    The provider sends the browser back to a plain URL, while the app keeps its
    token in ``localStorage`` — so something has to bridge the two. Putting the
    real 30-day token in the redirect would write a long-lived credential into
    the browser's history; a single-use code that expires in two minutes does
    not.

    In process and therefore lost on restart, which is the right trade here:
    the app runs one worker, and losing an in-flight login means clicking the
    button again.
    """

    def __init__(self) -> None:
        self._codes: dict[str, tuple[int, float]] = {}

    def _sweep(self, now: float) -> None:
        expired = [c for c, (_, ts) in self._codes.items() if now - ts > HANDOFF_TTL_SECONDS]
        for code in expired:
            self._codes.pop(code, None)

    def issue(self, user_id: int) -> str:
        now = time.monotonic()
        self._sweep(now)
        code = secrets.token_urlsafe(32)
        self._codes[code] = (user_id, now)
        return code

    def redeem(self, code: str) -> int | None:
        now = time.monotonic()
        self._sweep(now)
        entry = self._codes.pop(code, None)  # single use, even on a stale code
        if entry is None:
            return None
        user_id, issued = entry
        if now - issued > HANDOFF_TTL_SECONDS:
            return None
        return user_id


handoffs = HandoffStore()
