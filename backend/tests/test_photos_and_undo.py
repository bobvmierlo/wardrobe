"""Photo access control, and undoing an adopted outfit in one request.

Photos used to be a plain static mount: whoever held the URL could fetch the
file, logged in or not. These tests pin down that the file now follows the
sharing rules of the wardrobe its garment belongs to.
"""

import io
import uuid

from PIL import Image

ADMIN_USER = "admin"
ADMIN_PASS = "changeme"


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, username: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def make_user(client, admin_token: str, display: str):
    username = "u_" + uuid.uuid4().hex[:10]
    password = "pw123456"
    r = client.post(
        "/api/users",
        headers=h(admin_token),
        json={"username": username, "display_name": display, "password": password, "is_admin": False},
    )
    assert r.status_code == 201, r.text
    return username, password


def own_wardrobe_id(client, token: str) -> int:
    r = client.get("/api/wardrobes", headers=h(token))
    assert r.status_code == 200, r.text
    return [w for w in r.json() if w["my_role"] == "owner"][0]["id"]


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (120, 140, 160)).save(buf, "JPEG")
    return buf.getvalue()


def add_item_with_photo(client, token: str, wardrobe_id: int, name: str, category: str, **extra):
    data = {"wardrobe_id": str(wardrobe_id), "name": name, "category": category}
    data.update({k: str(v) for k, v in extra.items()})
    r = client.post(
        "/api/items",
        headers=h(token),
        data=data,
        files={"photo": ("p.jpg", _jpeg(), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_photo_needs_a_login_and_respects_wardrobe_access(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    au, ap = make_user(client, admin, "Alice")
    bu, bp = make_user(client, admin, "Bob")
    alice = login(client, au, ap)
    bob = login(client, bu, bp)

    item = add_item_with_photo(client, alice, own_wardrobe_id(client, alice), "Blauw hemd", "Overhemd")
    url = f"/uploads/{item['photo_filename']}"

    # No credentials at all: the URL alone is not enough any more.
    assert client.get(url, headers={"Cookie": ""}).status_code == 401

    # Alice owns it.
    r = client.get(url, headers=h(alice))
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"

    # Bob has no access to Alice's kast, even holding the exact filename.
    assert client.get(url, headers=h(bob)).status_code == 403

    # An admin reaches every wardrobe, so an admin reaches every photo.
    assert client.get(url, headers=h(admin)).status_code == 200

    # The thumbnail is guarded the same way.
    thumb = f"/uploads/{item['thumb_filename']}"
    assert client.get(thumb, headers=h(bob)).status_code == 403
    assert client.get(thumb, headers=h(alice)).status_code == 200


def test_photo_cookie_authorises_an_img_request(client):
    """<img> cannot send a bearer token, so login hands out a cookie instead."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    au, ap = make_user(client, admin, "Cookie Claire")

    r = client.post("/api/auth/login", data={"username": au, "password": ap})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert "wardrobe_photo" in r.cookies

    item = add_item_with_photo(client, token, own_wardrobe_id(client, token), "Rok", "Rok")
    url = f"/uploads/{item['photo_filename']}"

    # The client kept the cookie from logging in; no Authorization header here.
    assert client.get(url).status_code == 200

    client.post("/api/auth/logout")
    assert client.get(url).status_code == 401


def test_unknown_photo_is_not_found(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    assert client.get(f"/uploads/{uuid.uuid4().hex}.jpg", headers=h(admin)).status_code == 404


def test_undo_suggestion_clears_every_pair_in_one_request(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    au, ap = make_user(client, admin, "Outfit Otto")
    token = login(client, au, ap)
    wid = own_wardrobe_id(client, token)

    names = [("Wit overhemd", "Overhemd"), ("Blauwe jeans", "Jeans"), ("Bruine riem", "Riem")]
    ids = [
        add_item_with_photo(client, token, wid, n, c, season="Alle seizoenen")["id"]
        for n, c in names
    ]

    r = client.post("/api/matches/suggestions/accept", headers=h(token), json={"item_ids": ids})
    assert r.status_code == 204, r.text
    judged = client.get(f"/api/matches/judged?wardrobe_id={wid}", headers=h(token)).json()
    assert len(judged) == 3  # every pair of the three-piece outfit

    r = client.post("/api/matches/suggestions/undo", headers=h(token), json={"item_ids": ids})
    assert r.status_code == 204, r.text
    assert client.get(f"/api/matches/judged?wardrobe_id={wid}", headers=h(token)).json() == []


def test_undo_suggestion_refuses_someone_elses_wardrobe(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    au, ap = make_user(client, admin, "Owner Olga")
    bu, bp = make_user(client, admin, "Stranger Sam")
    olga = login(client, au, ap)
    sam = login(client, bu, bp)
    wid = own_wardrobe_id(client, olga)

    ids = [
        add_item_with_photo(client, olga, wid, n, c, season="Alle seizoenen")["id"]
        for n, c in [("Groene trui", "Trui"), ("Zwarte chino", "Chino")]
    ]
    assert (
        client.post("/api/matches/suggestions/undo", headers=h(sam), json={"item_ids": ids}).status_code
        == 403
    )
