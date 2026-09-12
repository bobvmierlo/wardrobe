"""The locks on the front door.

Five things, each of which was missing: proving you know your current password
before changing it, tokens that can actually be revoked, a password minimum
worth having, a login that slows down under guessing, and a server that refuses
to fetch URLs pointing back into its own network.
"""

import socket
import uuid

import httpx
import pytest

from app import fetching
from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.security import create_access_token
from app.throttle import LoginThrottle, client_key, login_throttle

GOOD_PASSWORD = "een-lang-genoeg-wachtwoord"


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, username: str, password: str):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def admin_token(client) -> str:
    login_throttle.reset()
    return login(client, "admin", "changeme").json()["access_token"]


def make_user(client, *, password: str = GOOD_PASSWORD, is_admin: bool = False) -> tuple[str, str]:
    """A fresh account, and a token for it."""
    username = "h_" + uuid.uuid4().hex[:8]
    response = client.post(
        "/api/users",
        headers=h(admin_token(client)),
        json={
            "username": username,
            "display_name": "Hardening " + username,
            "password": password,
            "is_admin": is_admin,
        },
    )
    assert response.status_code == 201, response.text
    login_throttle.reset()
    return username, login(client, username, password).json()["access_token"]


@pytest.fixture(autouse=True)
def _no_leftover_throttling():
    """Each test starts with the door unlocked, and leaves it that way."""
    login_throttle.reset()
    yield
    login_throttle.reset()


# ---------------------------------------------------------------------------
# changing a password
# ---------------------------------------------------------------------------

def test_changing_a_password_requires_the_current_one(client):
    _username, token = make_user(client)

    # Without it: a borrowed unlocked phone must not be able to take the account.
    naked = client.post(
        "/api/auth/change-password", headers=h(token), json={"new_password": "iets-anders-lang"}
    )
    assert naked.status_code == 403
    assert "huidige wachtwoord" in naked.json()["detail"]

    wrong = client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": "niet-het-juiste", "new_password": "iets-anders-lang"},
    )
    assert wrong.status_code == 403

    ok = client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": GOOD_PASSWORD, "new_password": "iets-anders-lang"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]


def test_reusing_the_same_password_is_refused(client):
    _username, token = make_user(client)
    response = client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": GOOD_PASSWORD, "new_password": GOOD_PASSWORD},
    )
    assert response.status_code == 400
    assert "hetzelfde" in response.json()["detail"]


def test_a_refused_password_change_is_recorded(client):
    username, token = make_user(client)
    client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": "mis", "new_password": "iets-anders-lang"},
    )
    trail = client.get(
        "/api/audit",
        headers=h(admin_token(client)),
        params={"action": "auth.password_change_failed"},
    ).json()
    assert trail["total"] >= 1
    assert any(username in e["detail"] or "Hardening" in e["detail"] for e in trail["entries"])


def test_an_account_without_a_password_may_set_a_first_one(client):
    """An SSO-only account has nothing to prove; it is adding a break-glass."""
    db = SessionLocal()
    try:
        user = User(
            username="sso_only_" + uuid.uuid4().hex[:6],
            display_name="Alleen SSO",
            hashed_password="!sso",
            auth_provider="oidc",
            oidc_subject="sub-" + uuid.uuid4().hex,
        )
        db.add(user)
        db.commit()
        user_id, username = user.id, user.username
        token = create_access_token(user_id, token_version=user.token_version)
    finally:
        db.close()

    response = client.post(
        "/api/auth/change-password", headers=h(token), json={"new_password": GOOD_PASSWORD}
    )
    assert response.status_code == 200, response.text
    # And now it can sign in with a password, which it could not before.
    assert login(client, username, GOOD_PASSWORD).status_code == 200


# ---------------------------------------------------------------------------
# tokens that can be taken away
# ---------------------------------------------------------------------------

def test_changing_a_password_ends_every_other_session(client):
    _username, token = make_user(client)
    assert client.get("/api/auth/me", headers=h(token)).status_code == 200

    changed = client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": GOOD_PASSWORD, "new_password": "een-nieuw-lang-woord"},
    )
    fresh = changed.json()["access_token"]

    # The token that knew the old password is done. This is the whole point: a
    # password change is what you do *because* you think someone has one.
    assert client.get("/api/auth/me", headers=h(token)).status_code == 401
    # The device you changed it on stays signed in.
    assert client.get("/api/auth/me", headers=h(fresh)).status_code == 200


def test_logging_out_everywhere_keeps_only_this_session(client):
    username, first = make_user(client)
    second = login(client, username, GOOD_PASSWORD).json()["access_token"]
    assert client.get("/api/auth/me", headers=h(second)).status_code == 200

    response = client.post("/api/auth/logout-everywhere", headers=h(second))
    assert response.status_code == 200
    kept = response.json()["access_token"]

    assert client.get("/api/auth/me", headers=h(first)).status_code == 401
    assert client.get("/api/auth/me", headers=h(second)).status_code == 401
    assert client.get("/api/auth/me", headers=h(kept)).status_code == 200


def test_a_revoked_token_stops_serving_photos_too(client):
    """Both doors, one answer: revocation that photos ignore is not revocation."""
    username, token = make_user(client)
    own = next(
        w for w in client.get("/api/wardrobes", headers=h(token)).json()
        if w["my_role"] == "owner"
    )
    created = client.post(
        "/api/items",
        headers=h(token),
        data={"wardrobe_id": own["id"], "name": "Trui", "category": "Trui"},
        files={"photo": ("t.jpg", _one_pixel_jpeg(), "image/jpeg")},
    )
    assert created.status_code == 201, created.text
    filename = created.json()["photo_filename"]
    assert filename

    # Reachable with the cookie the login handed out...
    assert client.get(f"/uploads/{filename}").status_code == 200

    fresh = login(client, username, GOOD_PASSWORD).json()["access_token"]
    client.post("/api/auth/logout-everywhere", headers=h(fresh))
    # ...and not with the one that is now revoked.
    assert client.get(f"/uploads/{filename}", headers=h(token)).status_code == 401
    client.cookies.clear()
    assert client.get(f"/uploads/{filename}").status_code == 401


def test_a_token_from_before_versioning_still_works(client):
    """Nobody is signed out by the upgrade itself."""
    import jwt
    from datetime import datetime, timedelta, timezone

    username, _token = make_user(client)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        assert user.token_version == 1
        legacy = jwt.encode(
            {
                "sub": str(user.id),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            settings.secret_key,
            algorithm="HS256",
        )
    finally:
        db.close()
    assert client.get("/api/auth/me", headers=h(legacy)).status_code == 200


def _one_pixel_jpeg() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (120, 120, 120)).save(buffer, format="JPEG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# password length
# ---------------------------------------------------------------------------

def test_a_short_password_is_refused_everywhere_one_is_set(client):
    short = "kort1"
    created = client.post(
        "/api/users",
        headers=h(admin_token(client)),
        json={
            "username": "tooshort",
            "display_name": "Te Kort",
            "password": short,
            "is_admin": False,
        },
    )
    assert created.status_code == 422

    _username, token = make_user(client)
    changed = client.post(
        "/api/auth/change-password",
        headers=h(token),
        json={"current_password": GOOD_PASSWORD, "new_password": short},
    )
    assert changed.status_code == 422


def test_the_login_screen_is_told_the_minimum(client):
    body = client.get("/api/auth/config").json()
    assert body["min_password_length"] == settings.min_password_length
    assert body["min_password_length"] >= 8


def test_an_existing_short_password_still_signs_in(client):
    """Raising the minimum must not lock anyone out of their own wardrobe.

    The rule applies where a password is *set*, never where one is checked, so
    an account whose password predates the rule keeps working. Stored straight
    into the database on purpose: that is what an older install looks like, and
    going through the API would (correctly) refuse it.
    """
    from app.security import hash_password

    short = "kort"
    assert len(short) < settings.min_password_length
    username = "oldtimer_" + uuid.uuid4().hex[:6]
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                display_name="Van Vroeger",
                hashed_password=hash_password(short),
            )
        )
        db.commit()
    finally:
        db.close()

    assert login(client, username, short).status_code == 200
    # …while setting a new one still has to meet the rule.
    created = client.post(
        "/api/users",
        headers=h(admin_token(client)),
        json={
            "username": "newcomer_" + uuid.uuid4().hex[:6],
            "display_name": "Nieuw",
            "password": short,
            "is_admin": False,
        },
    )
    assert created.status_code == 422


# ---------------------------------------------------------------------------
# guessing passwords
# ---------------------------------------------------------------------------

def test_repeated_failures_start_getting_429(client):
    username, _token = make_user(client)
    for attempt in range(settings.login_max_attempts):
        assert login(client, username, "fout-wachtwoord").status_code == 401, attempt

    blocked = login(client, username, "fout-wachtwoord")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    # Even the right password has to wait — otherwise the block is decoration.
    assert login(client, username, GOOD_PASSWORD).status_code == 429


def test_a_block_is_recorded_so_a_beheerder_can_see_it(client):
    username, _token = make_user(client)
    for _ in range(settings.login_max_attempts + 1):
        login(client, username, "fout-wachtwoord")
    login_throttle.reset()
    trail = client.get(
        "/api/audit", headers=h(admin_token(client)), params={"action": "auth.login_throttled"}
    ).json()
    assert trail["total"] >= 1


def test_a_correct_password_forgives_the_typos_before_it(client):
    username, _token = make_user(client)
    for _ in range(settings.login_max_attempts - 1):
        assert login(client, username, "typefout").status_code == 401
    assert login(client, username, GOOD_PASSWORD).status_code == 200
    # The counter is clear, so the next slip does not land on a full count.
    assert login(client, username, "typefout").status_code == 401
    assert login(client, username, GOOD_PASSWORD).status_code == 200


def test_the_wait_doubles_and_is_capped():
    throttle = LoginThrottle(max_attempts=2, base_seconds=10, max_seconds=40)
    assert throttle.retry_after("user:a") == 0
    throttle.record_failure("user:a")
    assert throttle.retry_after("user:a") == 0      # still within the allowance
    throttle.record_failure("user:a")
    first = throttle.retry_after("user:a")
    assert 0 < first <= 11
    throttle.record_failure("user:a")
    assert throttle.retry_after("user:a") > first   # doubled
    for _ in range(10):
        throttle.record_failure("user:a")
    assert throttle.retry_after("user:a") <= 41     # capped


def test_one_account_being_blocked_does_not_block_another():
    throttle = LoginThrottle(max_attempts=1, base_seconds=10)
    throttle.record_failure("user:a")
    throttle.record_failure("user:a")
    assert throttle.retry_after("user:a") > 0
    assert throttle.retry_after("user:b") == 0


def test_a_forwarded_address_is_preferred_over_the_proxy_itself():
    # Behind nginx every request comes from 127.0.0.1, which would make one
    # shared counter for the whole world.
    assert client_key("127.0.0.1", "203.0.113.9, 10.0.0.1") == "ip:203.0.113.9"
    assert client_key("203.0.113.9", None) == "ip:203.0.113.9"
    assert client_key(None, "") == "ip:onbekend"


# ---------------------------------------------------------------------------
# headers and origins
# ---------------------------------------------------------------------------

def test_no_cross_origin_access_is_handed_out_by_default(client):
    response = client.get("/api/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_the_app_sends_the_headers_that_protect_it(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers["content-security-policy"]
    # The token lives in localStorage, so "no scripts but ours" is the point.
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


def test_hsts_is_only_promised_when_asked_for_and_over_https(client, monkeypatch):
    assert "strict-transport-security" not in {
        k.lower() for k in client.get("/api/health").headers
    }
    monkeypatch.setattr(settings, "hsts_seconds", 31536000)
    plain = client.get("/api/health")
    assert "strict-transport-security" not in {k.lower() for k in plain.headers}
    secure = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert secure.headers["strict-transport-security"] == "max-age=31536000"


# ---------------------------------------------------------------------------
# fetching URLs somebody typed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:9000/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",   # cloud metadata
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
    ],
)
def test_the_server_refuses_to_visit_its_own_network(url):
    with pytest.raises(fetching.FetchRefused):
        fetching._check_target(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.test/x", "gopher://x/"])
def test_only_http_and_https_are_fetched(url):
    with pytest.raises(fetching.FetchRefused):
        fetching._check_target(url)


def _resolve_to(monkeypatch, mapping: dict[str, str]):
    """Pretend DNS says what the test wants it to say."""
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        if host in mapping:
            address = mapping[host]
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_a_public_address_is_allowed(monkeypatch):
    _resolve_to(monkeypatch, {"shop.test": "93.184.216.34"})
    fetching._check_target("https://shop.test/product/1")  # does not raise


def test_a_name_that_resolves_inward_is_refused(monkeypatch):
    """The DNS-rebinding shape: a public-looking name pointing at the LAN."""
    _resolve_to(monkeypatch, {"sneaky.test": "192.168.8.8"})
    with pytest.raises(fetching.FetchRefused):
        fetching._check_target("https://sneaky.test/")


def test_allow_private_opens_it_for_operators_who_mean_it(monkeypatch):
    _resolve_to(monkeypatch, {"nas.test": "192.168.8.8"})
    monkeypatch.setattr(settings, "fetch_allow_private", True)
    fetching._check_target("http://nas.test/photo.jpg")  # does not raise


def _transport(monkeypatch, handler):
    monkeypatch.setattr(
        fetching, "_client", lambda timeout: httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_a_redirect_into_the_private_network_is_refused(monkeypatch):
    """The obvious way around a check that only looks at what was typed."""
    _resolve_to(monkeypatch, {"shop.test": "93.184.216.34"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "shop.test":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        return httpx.Response(200, content=b"secrets")

    _transport(monkeypatch, handler)
    with pytest.raises(fetching.FetchRefused):
        fetching.fetch_remote("https://shop.test/p", limit=1024)


def test_a_redirect_to_a_public_address_is_followed(monkeypatch):
    _resolve_to(monkeypatch, {"shop.test": "93.184.216.34", "www.shop.test": "93.184.216.34"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "shop.test":
            return httpx.Response(301, headers={"location": "https://www.shop.test/p"})
        return httpx.Response(
            200, content=b"<html>hoi</html>", headers={"content-type": "text/html"}
        )

    _transport(monkeypatch, handler)
    fetched = fetching.fetch_remote("https://shop.test/p", limit=4096)
    assert fetched.body == b"<html>hoi</html>"
    assert fetched.url == "https://www.shop.test/p"


def test_an_endless_redirect_chain_gives_up(monkeypatch):
    _resolve_to(monkeypatch, {"loop.test": "93.184.216.34"})
    _transport(
        monkeypatch,
        lambda request: httpx.Response(302, headers={"location": "https://loop.test/again"}),
    )
    with pytest.raises(fetching.FetchFailed):
        fetching.fetch_remote("https://loop.test/", limit=1024)


def test_a_body_past_the_cap_is_an_error_not_a_truncation(monkeypatch):
    _resolve_to(monkeypatch, {"big.test": "93.184.216.34"})
    _transport(monkeypatch, lambda request: httpx.Response(200, content=b"x" * 5000))
    with pytest.raises(fetching.FetchFailed, match="te groot"):
        fetching.fetch_remote("https://big.test/", limit=1000)


def test_an_error_from_the_far_end_keeps_its_status(monkeypatch):
    _resolve_to(monkeypatch, {"shop.test": "93.184.216.34"})
    _transport(monkeypatch, lambda request: httpx.Response(403, content=b"no bots"))
    with pytest.raises(fetching.FetchFailed) as raised:
        fetching.fetch_remote("https://shop.test/", limit=1024)
    assert raised.value.status == 403


def test_the_webshop_import_refuses_a_private_url(client):
    _username, token = make_user(client)
    response = client.get(
        "/api/import/scrape", headers=h(token), params={"url": "http://169.254.169.254/latest/"}
    )
    # 400 and the real reason, not a 502 that sends someone debugging a webshop.
    assert response.status_code == 400
    assert "eigen netwerk" in response.json()["detail"]


def test_adding_a_garment_by_private_photo_url_is_refused(client):
    _username, token = make_user(client)
    own = next(
        w for w in client.get("/api/wardrobes", headers=h(token)).json()
        if w["my_role"] == "owner"
    )
    response = client.post(
        "/api/items",
        headers=h(token),
        data={
            "wardrobe_id": own["id"],
            "name": "Broek",
            "category": "Broek",
            "photo_url": "http://127.0.0.1:8000/secret.jpg",
        },
    )
    assert response.status_code == 400
    assert "eigen netwerk" in response.json()["detail"]
