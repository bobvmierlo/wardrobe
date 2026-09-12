"""Federated login, against a provider that only exists in this file.

The fake provider is deliberately thin but *real* where it counts: the ID
tokens are genuinely signed with a genuine RSA key and verified by the genuine
code path, so a mistake in the signature, issuer, audience or nonce checks
fails a test here rather than in production. Only the network is faked.
"""

import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app import oidc
from app.config import settings
from app.routers.oidc import STATE_COOKIE, _safe_next
from app.database import SessionLocal
from app.models import User, Wardrobe, WardrobeMember

ISSUER = "https://idp.test/application/o/kledingkast"
CLIENT_ID = "kledingkast"
CLIENT_SECRET = "s3cret"

DOCUMENT = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/authorize",
    "token_endpoint": f"{ISSUER}/token",
    "userinfo_endpoint": f"{ISSUER}/userinfo",
    "jwks_uri": f"{ISSUER}/jwks",
    "end_session_endpoint": f"{ISSUER}/end-session",
    "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
    "id_token_signing_alg_values_supported": ["RS256"],
}


class FakeIdp:
    """Everything the app needs a provider to be, with no sockets involved."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        #: Which key id the provider claims to sign with, and which one it
        #: publishes. Normally the same; a rotation makes them differ for a
        #: moment.
        self.kid = "key-1"
        self.published_kid = "key-1"
        # What the next token endpoint call will hand back, and what userinfo
        # will say. Tests set these before driving the callback.
        self.claims: dict = {}
        self.userinfo: dict = {}
        self.sign_with_wrong_key = False
        self.omit_id_token = False
        self.reject_basic_auth = False
        self.omit_kid = False
        #: Status the JWKS endpoint answers with, and how many times it was
        #: asked. 403 is the case that sent a real login into a wrong-looking
        #: error about the issuer URL.
        self.jwks_status = 200
        self.jwks_keys_override: list | None = None
        self.token_requests: list[dict] = []
        self.jwks_requests: list[dict] = []

    # -- signing ---------------------------------------------------------
    def sign(self, claims: dict) -> str:
        key = self.other_key if self.sign_with_wrong_key else self.key
        headers = None if self.omit_kid else {"kid": self.kid}
        return jwt.encode(claims, key, algorithm="RS256", headers=headers)

    def jwks_document(self) -> dict:
        if self.jwks_keys_override is not None:
            return {"keys": self.jwks_keys_override}
        jwk = RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {
            "keys": [
                {**jwk, "kid": self.published_kid, "use": "sig", "alg": "RS256"}
            ]
        }

    def base_claims(self, *, sub: str, nonce: str, **extra) -> dict:
        now = int(time.time())
        return {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": sub,
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            **extra,
        }

    # -- transport -------------------------------------------------------
    def handle(self, request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path.endswith("/token"):
            body = parse_qs(request.content.decode())
            self.token_requests.append(
                {
                    "body": {k: v[0] for k, v in body.items()},
                    "auth": request.headers.get("authorization", ""),
                }
            )
            if self.reject_basic_auth and request.headers.get("authorization"):
                return httpx.Response(401, json={"error": "invalid_client"})
            payload: dict = {"access_token": "fake-access-token", "token_type": "Bearer"}
            if not self.omit_id_token:
                payload["id_token"] = self.sign(self.claims)
            return httpx.Response(200, json=payload)
        if path.endswith("/userinfo"):
            return httpx.Response(200, json=self.userinfo)
        if path.endswith("/jwks"):
            self.jwks_requests.append(
                {"user_agent": request.headers.get("user-agent", "")}
            )
            if self.jwks_status != 200:
                return httpx.Response(self.jwks_status, text="Forbidden")
            return httpx.Response(200, json=self.jwks_document())
        return httpx.Response(404, json={"error": "not_found"})

    def client(self) -> httpx.Client:
        # Mirrors the real client's headers, so a test can tell that a request
        # went through app code rather than around it.
        return httpx.Client(
            transport=httpx.MockTransport(self.handle),
            headers={"User-Agent": oidc.USER_AGENT},
        )


@pytest.fixture
def idp(monkeypatch):
    """A configured provider, wired into the app for the duration of one test."""
    fake = FakeIdp()
    monkeypatch.setattr(settings, "oidc_enabled", True)
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "oidc_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "oidc_scopes", "openid profile email groups")
    monkeypatch.setattr(settings, "oidc_groups_claim", "groups")
    monkeypatch.setattr(settings, "oidc_admin_group", "")
    monkeypatch.setattr(settings, "oidc_allowed_groups", "")
    monkeypatch.setattr(settings, "oidc_auto_create", False)
    monkeypatch.setattr(settings, "oidc_link_by_username", False)
    monkeypatch.setattr(oidc, "_client", fake.client)
    monkeypatch.setattr(
        oidc,
        "_fetch_discovery",
        lambda: oidc._Discovery(document=DOCUMENT, fetched_at=time.monotonic()),
    )
    oidc.reset_cache()
    yield fake
    oidc.reset_cache()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def start_login(client, **params) -> tuple[str, str]:
    """Do the first leg and return the (state, nonce) the app generated."""
    client.cookies.clear()
    response = client.get("/api/auth/oidc/login", params=params, follow_redirects=False)
    assert response.status_code == 303, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0], query["nonce"][0]


def finish_login(client, idp: FakeIdp, *, sub: str, state: str, nonce: str, **claims):
    """Drive the callback with an ID token the fake provider just signed."""
    idp.claims = idp.base_claims(sub=sub, nonce=nonce, **claims)
    return client.get(
        "/api/auth/oidc/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )


def sso_login(client, idp: FakeIdp, *, sub: str, invite: str | None = None, **claims):
    """The whole round trip, ending in an app token. Returns (token, user)."""
    params = {"invite": invite} if invite else {}
    state, nonce = start_login(client, **params)
    response = finish_login(client, idp, sub=sub, state=state, nonce=nonce, **claims)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert "oidc_error" not in location, unquote(location)
    code = parse_qs(urlparse(location).fragment)["oidc"][0]
    exchanged = client.post("/api/auth/oidc/exchange", json={"code": code})
    assert exchanged.status_code == 200, exchanged.text
    body = exchanged.json()
    return body["access_token"], body["user"]


def error_of(response) -> str:
    return unquote(urlparse(response.headers["location"]).fragment)


def _admin_token(client) -> str:
    return client.post(
        "/api/auth/login", data={"username": "admin", "password": "changeme"}
    ).json()["access_token"]


def make_local_user(
    client, username: str, *, password: str = "een-wachtwoord", is_admin: bool = False
) -> dict:
    """An ordinary password account, created the way a beheerder would."""
    response = client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {_admin_token(client)}"},
        json={
            "username": username,
            "display_name": username.title(),
            "password": password,
            "is_admin": is_admin,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def db_user(sub: str) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.oidc_subject == sub).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# the front door
# ---------------------------------------------------------------------------

def test_config_hides_sso_until_it_is_configured(client):
    body = client.get("/api/auth/config").json()
    assert body["oidc_enabled"] is False
    assert body["oidc_label"] == ""
    # The password form is always offered by default — that is the break-glass.
    assert body["local_login"] is True


def test_config_advertises_sso_when_configured(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_button_label", "Inloggen met Authentik")
    body = client.get("/api/auth/config").json()
    assert body["oidc_enabled"] is True
    assert body["oidc_label"] == "Inloggen met Authentik"
    # No hint about which provider beyond the label the operator chose.
    assert ISSUER not in str(body)


def test_half_configured_sso_stays_off(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_enabled", True)
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "oidc_client_secret", "")
    assert client.get("/api/auth/config").json()["oidc_enabled"] is False
    assert client.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404


def test_login_sends_the_browser_to_the_provider_with_pkce(client, idp):
    response = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 303
    url = urlparse(response.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == DOCUMENT["authorization_endpoint"]
    query = parse_qs(url.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert "openid" in query["scope"][0]
    assert "groups" in query["scope"][0]
    assert query["redirect_uri"] == ["http://testserver/api/auth/oidc/callback"]
    assert STATE_COOKIE in response.cookies


def test_open_redirect_is_refused():
    # "next" comes from a query string, so it must never leave the app: an open
    # redirect on a login route is how phishing gets the address bar right.
    assert _safe_next("https://evil.test") == "/"
    assert _safe_next("//evil.test") == "/"
    assert _safe_next("javascript:alert(1)") == "/"
    assert _safe_next("/outfits") == "/outfits"
    assert _safe_next(None) == "/"


# ---------------------------------------------------------------------------
# who gets in
# ---------------------------------------------------------------------------

def test_unknown_person_is_turned_away_while_the_door_is_shut(client, idp):
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="stranger", state=state, nonce=nonce,
        preferred_username="stranger",
    )
    assert response.status_code == 303
    assert "nog geen account" in error_of(response)
    assert db_user("stranger") is None


def test_auto_create_provisions_an_ordinary_user(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    _token, user = sso_login(
        client, idp, sub="newbie",
        preferred_username="Newbie", name="New Bie", email="newbie@test",
    )
    assert user["username"] == "newbie"
    assert user["display_name"] == "New Bie"
    assert user["is_admin"] is False
    assert user["auth_provider"] == "oidc"
    # Every account owns a kast, invited or provisioned.
    db = SessionLocal()
    try:
        assert db.query(Wardrobe).filter(Wardrobe.owner_id == user["id"]).count() == 1
    finally:
        db.close()


def test_the_same_subject_comes_back_to_the_same_account(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    _t, first = sso_login(client, idp, sub="stable", preferred_username="stable")
    # A rename at the provider must not create a second account, and must not
    # reach a different one either: the sub is what identifies the person.
    _t, again = sso_login(
        client, idp, sub="stable", preferred_username="renamed", name="Renamed"
    )
    assert again["id"] == first["id"]
    assert again["username"] == "stable"       # username is left alone
    assert again["display_name"] == "Renamed"  # display name follows the provider


def test_an_sso_account_has_no_password_to_guess(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    sso_login(client, idp, sub="nopass", preferred_username="nopass")
    for attempt in ("!sso", "changeme", "password", "nopass"):
        response = client.post(
            "/api/auth/login", data={"username": "nopass", "password": attempt}
        )
        assert response.status_code == 401, attempt


def test_local_login_keeps_working_while_sso_is_on(client, idp):
    """The whole point of the break-glass: SSO on does not close the door."""
    response = client.post(
        "/api/auth/login", data={"username": "admin", "password": "changeme"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["auth_provider"] == "local"


def test_allowed_groups_gate_the_installation(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_allowed_groups", "kledingkast-users")
    state, nonce = start_login(client)
    refused = finish_login(
        client, idp, sub="outsider", state=state, nonce=nonce,
        preferred_username="outsider", groups=["something-else"],
    )
    assert "mag deze Kledingkast niet gebruiken" in error_of(refused)
    assert db_user("outsider") is None

    _t, user = sso_login(
        client, idp, sub="insider", preferred_username="insider",
        groups=["kledingkast-users"],
    )
    assert user["username"] == "insider"


def test_link_by_username_adopts_an_account_that_predates_sso(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_link_by_username", True)
    make_local_user(client, "legacy", password="oud-wachtwoord")

    _t, user = sso_login(client, idp, sub="legacy-sub", preferred_username="legacy")
    assert user["username"] == "legacy"   # adopted, not duplicated
    assert user["auth_provider"] == "oidc"
    # …and its local password still works, because that is the break-glass.
    assert client.post(
        "/api/auth/login", data={"username": "legacy", "password": "oud-wachtwoord"}
    ).status_code == 200


# ---------------------------------------------------------------------------
# the group → beheerder mapping
# ---------------------------------------------------------------------------

def test_admin_group_grants_and_revokes_the_role(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "kledingkast-admins")

    _t, user = sso_login(
        client, idp, sub="boss", preferred_username="boss",
        groups=["kledingkast-admins", "staff"],
    )
    assert user["is_admin"] is True

    # Removed from the group at the provider: an ordinary user again on the
    # next sign-in. This is the behaviour the mapping exists for.
    _t, user = sso_login(
        client, idp, sub="boss", preferred_username="boss", groups=["staff"]
    )
    assert user["is_admin"] is False


def test_group_matching_ignores_case(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "Kledingkast-Admins")
    _t, user = sso_login(
        client, idp, sub="casey", preferred_username="casey",
        groups=["kledingkast-admins"],
    )
    assert user["is_admin"] is True


def test_no_admin_group_configured_means_no_role_changes(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "")
    monkeypatch.setattr(settings, "oidc_link_by_username", True)
    make_local_user(client, "keeper", is_admin=True)
    # A beheerder signs in through the provider and stays one, even though no
    # group says so: with the mapping off, roles are the app's to manage.
    _t, user = sso_login(client, idp, sub="keeper-sub", preferred_username="keeper")
    assert user["username"] == "keeper"
    assert user["is_admin"] is True


def test_groups_are_read_from_userinfo_when_absent_from_the_id_token(
    client, idp, monkeypatch
):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "kledingkast-admins")
    idp.userinfo = {"sub": "ui", "groups": ["kledingkast-admins"]}
    _t, user = sso_login(client, idp, sub="ui", preferred_username="ui")
    assert user["is_admin"] is True


def test_a_nested_claim_path_works(client, idp, monkeypatch):
    """Keycloak puts realm roles in realm_access.roles, not in "groups"."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_groups_claim", "realm_access.roles")
    monkeypatch.setattr(settings, "oidc_admin_group", "wardrobe-admin")
    _t, user = sso_login(
        client, idp, sub="kc", preferred_username="kc",
        realm_access={"roles": ["wardrobe-admin", "offline_access"]},
    )
    assert user["is_admin"] is True


def test_a_missing_groups_claim_leaves_the_role_alone_and_says_so(
    client, idp, monkeypatch
):
    """The most common misconfiguration, and it must not look like "not an admin"."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "kledingkast-admins")
    idp.userinfo = {"sub": "quiet"}  # no groups anywhere

    _t, user = sso_login(client, idp, sub="quiet", preferred_username="quiet")
    assert user["is_admin"] is False  # a new account starts ordinary

    # Now make them an admin in the app, and sign in again with still no claim:
    # the role must survive, because "claim absent" is not "not in the group".
    db = SessionLocal()
    try:
        row = db.query(User).filter(User.oidc_subject == "quiet").first()
        row.is_admin = True
        db.commit()
    finally:
        db.close()

    _t, user = sso_login(client, idp, sub="quiet", preferred_username="quiet")
    assert user["is_admin"] is True

    # …and the trail says why, because silence here reads exactly like
    # "this person is not in the group".
    trail = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {_admin_token(client)}"},
        params={"action": "auth.oidc_groups_missing"},
    ).json()
    assert trail["total"] >= 1
    assert "groepen-scope" in trail["entries"][0]["detail"]


def test_the_last_beheerder_is_never_demoted_by_a_group_change():
    """A renamed group should cost one person a role, not lock everyone out."""
    db = SessionLocal()
    try:
        solo = User(
            username="solo-admin",
            display_name="Solo",
            hashed_password="!sso",
            is_admin=True,
            auth_provider="oidc",
            oidc_subject="solo-admin-sub",
        )
        db.add(solo)
        # Everyone else loses the role, so this account is the only one left.
        others = db.query(User).filter(User.is_admin.is_(True), User.id != solo.id).all()
        was_admin = [u.id for u in others]
        for other in others:
            other.is_admin = False
        db.commit()

        settings.oidc_admin_group = "kledingkast-admins"
        try:
            oidc.sync_admin(db, solo, ["not-the-admin-group"], claim_missing=False)
            db.commit()
            db.refresh(solo)
            assert solo.is_admin is True
        finally:
            settings.oidc_admin_group = ""
            # Put the installation back the way the other tests expect it.
            for user_id in was_admin:
                db.get(User, user_id).is_admin = True
            db.delete(solo)
            db.commit()
    finally:
        db.close()


def test_a_beheerder_cannot_hand_edit_a_role_the_provider_owns(
    client, idp, monkeypatch
):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(settings, "oidc_admin_group", "kledingkast-admins")
    _t, user = sso_login(client, idp, sub="managed", preferred_username="managed")

    admin_token = client.post(
        "/api/auth/login", data={"username": "admin", "password": "changeme"}
    ).json()["access_token"]
    response = client.patch(
        f"/api/users/{user['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_admin": True},
    )
    # Accepting it would be a lie: the next SSO login puts it straight back.
    assert response.status_code == 400
    assert "identity provider" in response.json()["detail"]


# ---------------------------------------------------------------------------
# invitations
# ---------------------------------------------------------------------------

def test_an_invitation_lets_a_newcomer_in_through_sso(client, idp):
    """Auto-create stays off; the invitation is what authorises the account."""
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    wardrobes = client.get("/api/wardrobes", headers=headers).json()
    own = next(w for w in wardrobes if w["my_role"] == "owner")
    invitation = client.post(
        f"/api/wardrobes/{own['id']}/invitations",
        headers=headers,
        json={"role": "editor", "label": "Partner", "expires_days": 7},
    ).json()

    _t, user = sso_login(
        client, idp, sub="invited", invite=invitation["token"],
        preferred_username="invited", name="Invited Person",
    )
    assert user["username"] == "invited"
    assert user["is_admin"] is False

    db = SessionLocal()
    try:
        member = (
            db.query(WardrobeMember)
            .filter(
                WardrobeMember.wardrobe_id == own["id"],
                WardrobeMember.user_id == user["id"],
            )
            .first()
        )
        assert member is not None and member.role == "editor"
    finally:
        db.close()

    # One-time: the link is spent now.
    assert client.get(f"/api/invitations/{invitation['token']}").status_code == 410


def test_an_account_invitation_creates_a_login_and_nothing_else(client, idp):
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    invitation = client.post(
        "/api/invitations/account",
        headers=headers,
        json={"label": "Nieuw iemand", "expires_days": 7},
    ).json()

    _t, user = sso_login(
        client, idp, sub="account-invited", invite=invitation["token"],
        preferred_username="accountinvited",
    )
    db = SessionLocal()
    try:
        # Their own kast, and no access to anyone else's.
        assert db.query(Wardrobe).filter(Wardrobe.owner_id == user["id"]).count() == 1
        assert (
            db.query(WardrobeMember).filter(WardrobeMember.user_id == user["id"]).count()
            == 0
        )
    finally:
        db.close()


def test_a_spent_invitation_still_signs_a_known_person_in(client, idp, monkeypatch):
    """Authentication succeeded; a stale link is something to explain, not a refusal."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    sso_login(client, idp, sub="returning", preferred_username="returning")

    state, nonce = start_login(client, invite="no-such-invitation-token")
    response = finish_login(
        client, idp, sub="returning", state=state, nonce=nonce,
        preferred_username="returning",
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert "oidc_error" not in location
    # Sent to the invitation page, which says in its own words what is wrong.
    assert location.startswith("/invite/no-such-invitation-token#")


# ---------------------------------------------------------------------------
# what an attacker gets
# ---------------------------------------------------------------------------

def test_a_callback_without_the_state_cookie_is_refused(client, idp):
    state, _nonce = start_login(client)
    client.cookies.clear()
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "hoort niet bij deze browser" in error_of(response)


def test_a_mismatched_state_is_refused(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    _state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="forged", state="not-the-state", nonce=nonce,
        preferred_username="forged",
    )
    assert "hoort niet bij deze browser" in error_of(response)
    assert db_user("forged") is None


def test_a_replayed_nonce_is_refused(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    state, _nonce = start_login(client)
    response = finish_login(
        client, idp, sub="replay", state=state, nonce="a-nonce-from-an-older-login",
        preferred_username="replay",
    )
    assert "al gebruikt" in error_of(response)
    assert db_user("replay") is None


def test_an_id_token_signed_by_the_wrong_key_is_refused(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    idp.sign_with_wrong_key = True
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="spoofed", state=state, nonce=nonce,
        preferred_username="spoofed",
    )
    assert "niet geldig" in error_of(response)
    assert db_user("spoofed") is None


@pytest.mark.parametrize(
    "bad",
    [
        {"iss": "https://somewhere-else.test"},
        {"aud": "a-different-application"},
        {"exp": int(time.time()) - 60},
    ],
)
def test_a_token_for_somewhere_else_is_refused(client, idp, monkeypatch, bad):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    state, nonce = start_login(client)
    idp.claims = {**idp.base_claims(sub="elsewhere", nonce=nonce), **bad}
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "niet geldig" in error_of(response)
    assert db_user("elsewhere") is None


def test_a_provider_that_forgets_the_id_token_is_reported_clearly(client, idp):
    idp.omit_id_token = True
    state, nonce = start_login(client)
    idp.claims = idp.base_claims(sub="x", nonce=nonce)
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "openid" in error_of(response)


def test_the_providers_own_error_is_passed_on(client, idp):
    start_login(client)
    response = client.get(
        "/api/auth/oidc/callback",
        params={
            "error": "access_denied",
            "error_description": "Je bent niet toegewezen aan deze toepassing",
        },
        follow_redirects=False,
    )
    assert "niet toegewezen" in error_of(response)


def test_the_handoff_code_works_exactly_once(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="once", state=state, nonce=nonce, preferred_username="once"
    )
    code = parse_qs(urlparse(response.headers["location"]).fragment)["oidc"][0]
    assert client.post("/api/auth/oidc/exchange", json={"code": code}).status_code == 200
    second = client.post("/api/auth/oidc/exchange", json={"code": code})
    assert second.status_code == 400
    assert "verlopen" in second.json()["detail"]


def test_an_unknown_handoff_code_is_refused(client, idp):
    response = client.post(
        "/api/auth/oidc/exchange", json={"code": "definitely-not-a-real-code"}
    )
    assert response.status_code == 400


def test_an_expired_handoff_code_is_refused(monkeypatch):
    store = oidc.HandoffStore()
    code = store.issue(1)
    monkeypatch.setattr(oidc, "HANDOFF_TTL_SECONDS", -1)
    assert store.redeem(code) is None


# ---------------------------------------------------------------------------
# talking to the provider
# ---------------------------------------------------------------------------

def test_pkce_verifier_is_sent_and_matches_the_challenge(client, idp, monkeypatch):
    import base64
    import hashlib

    monkeypatch.setattr(settings, "oidc_auto_create", True)
    client.cookies.clear()
    started = client.get("/api/auth/oidc/login", follow_redirects=False)
    query = parse_qs(urlparse(started.headers["location"]).query)
    state, nonce = query["state"][0], query["nonce"][0]
    finish_login(client, idp, sub="pkce", state=state, nonce=nonce, preferred_username="pkce")

    sent = idp.token_requests[-1]["body"]
    assert sent["grant_type"] == "authorization_code"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(sent["code_verifier"].encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert expected == query["code_challenge"][0]


def test_a_provider_that_refuses_basic_auth_is_retried_with_a_form_secret(
    client, idp, monkeypatch
):
    """Providers disagree about where the secret goes; a login must not care."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    idp.reject_basic_auth = True
    _t, user = sso_login(client, idp, sub="fallback", preferred_username="fallback")
    assert user["username"] == "fallback"
    assert idp.token_requests[0]["auth"]                       # tried Basic first
    assert idp.token_requests[-1]["body"]["client_secret"] == CLIENT_SECRET


def test_an_unreachable_provider_does_not_take_the_app_down(client, monkeypatch):
    """Deliberately without the `idp` fixture: the real discovery path has to run."""
    monkeypatch.setattr(settings, "oidc_enabled", True)
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "oidc_client_secret", CLIENT_SECRET)

    def broken() -> httpx.Client:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        return httpx.Client(transport=httpx.MockTransport(refuse))

    monkeypatch.setattr(oidc, "_client", broken)
    oidc.reset_cache()

    response = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 303
    assert "niet bereikbaar" in error_of(response)

    # And the app is otherwise entirely fine, including the password door.
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.post(
        "/api/auth/login", data={"username": "admin", "password": "changeme"}
    ).status_code == 200


# ---------------------------------------------------------------------------
# fetching the signing keys
# ---------------------------------------------------------------------------
#
# The keys used to be fetched by PyJWT's own PyJWKClient, over urllib, with
# urllib's default User-Agent — while every other call to the provider went
# through httpx. A proxy in front of an identity provider answering that one
# request with 403 produced a login failure that blamed the issuer URL and the
# client id, both of which were fine. These are the tests for that.

def test_the_keys_are_fetched_through_the_apps_own_client(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    sso_login(client, idp, sub="keys", preferred_username="keys")
    assert idp.jwks_requests, "the key set was never fetched"
    # Same client, so the same identifiable User-Agent as every other call.
    assert idp.jwks_requests[0]["user_agent"] == oidc.USER_AGENT


def test_keys_that_cannot_be_fetched_blame_the_keys_and_not_the_issuer(
    client, idp, monkeypatch
):
    """The exact failure seen in production: JWKS answers 403."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    idp.jwks_status = 403
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="blocked", state=state, nonce=nonce, preferred_username="blocked"
    )
    message = error_of(response)
    assert "sleutels" in message
    assert "403" in message
    # The old message told you to check the issuer URL and the client id. This
    # one points at the keys and says those two are *not* the problem — which is
    # the whole difference between a five-minute fix and an evening.
    assert "Controleer de issuer-URL" not in message
    assert "níet in de issuer-URL of de client-id" in message
    assert db_user("blocked") is None


def test_a_provider_without_a_signing_key_is_told_to_set_one(client, idp, monkeypatch):
    """Authentik with no Signing Key publishes an empty set and signs HS256."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    idp.jwks_keys_override = []
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="nokey", state=state, nonce=nonce, preferred_username="nokey"
    )
    assert "Signing Key" in error_of(response)


def test_a_provider_that_only_offers_hs256_is_told_to_set_a_signing_key(
    client, idp, monkeypatch
):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(
        oidc,
        "_fetch_discovery",
        lambda: oidc._Discovery(
            document={**DOCUMENT, "id_token_signing_alg_values_supported": ["HS256"]},
            fetched_at=time.monotonic(),
        ),
    )
    oidc.reset_cache()
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="hs", state=state, nonce=nonce, preferred_username="hs"
    )
    message = error_of(response)
    assert "HS256" in message
    assert "Signing Key" in message


def test_a_rotated_key_is_picked_up_without_a_restart(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(oidc, "JWKS_MIN_REFETCH_SECONDS", 0)
    sso_login(client, idp, sub="rot", preferred_username="rot")
    fetched_before = len(idp.jwks_requests)

    # The provider starts signing with a new key id and publishes it.
    idp.kid = "key-2"
    idp.published_kid = "key-2"
    _token, user = sso_login(client, idp, sub="rot", preferred_username="rot")
    assert user["username"] == "rot"
    assert len(idp.jwks_requests) > fetched_before, "the key set was not re-fetched"


def test_an_unknown_key_that_stays_unknown_is_refused(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    monkeypatch.setattr(oidc, "JWKS_MIN_REFETCH_SECONDS", 0)
    # Signs with a kid it never publishes.
    idp.kid = "ghost"
    idp.published_kid = "key-1"
    state, nonce = start_login(client)
    response = finish_login(
        client, idp, sub="ghost", state=state, nonce=nonce, preferred_username="ghost"
    )
    assert "sleutel" in error_of(response)
    assert db_user("ghost") is None


def test_a_token_without_a_key_id_still_verifies(client, idp, monkeypatch):
    """Providers publishing exactly one key often omit the kid header."""
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    idp.omit_kid = True
    _token, user = sso_login(client, idp, sub="nokid", preferred_username="nokid")
    assert user["username"] == "nokid"


def test_the_key_set_is_cached_between_logins(client, idp, monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    sso_login(client, idp, sub="c1", preferred_username="c1")
    after_first = len(idp.jwks_requests)
    sso_login(client, idp, sub="c1", preferred_username="c1")
    assert len(idp.jwks_requests) == after_first, "keys re-fetched on every login"
