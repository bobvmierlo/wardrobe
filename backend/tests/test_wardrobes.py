"""Behavioural tests for per-user wardrobes, sharing and roles.

These share a single seeded database (session-scoped client), so each test
creates its own users with unique names instead of relying on a clean DB.
"""

import uuid

ADMIN_USER = "admin"
ADMIN_PASS = "changeme"


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, username: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def make_user(client, admin_token: str, display: str, is_admin: bool = False):
    username = "u_" + uuid.uuid4().hex[:10]
    password = "pw123456"
    r = client.post(
        "/api/users",
        headers=h(admin_token),
        json={"username": username, "display_name": display, "password": password, "is_admin": is_admin},
    )
    assert r.status_code == 201, r.text
    return r.json(), username, password


def own_wardrobe(client, token: str):
    r = client.get("/api/wardrobes", headers=h(token))
    assert r.status_code == 200, r.text
    wardrobes = r.json()
    owned = [w for w in wardrobes if w["my_role"] == "owner"]
    assert owned, "every user should own exactly one wardrobe"
    return owned[0], wardrobes


def add_item(client, token: str, wardrobe_id: int, name: str, category: str, **extra):
    data = {"wardrobe_id": str(wardrobe_id), "name": name, "category": category}
    data.update({k: str(v) for k, v in extra.items()})
    return client.post("/api/items", headers=h(token), data=data)


def test_admin_can_login(client):
    assert login(client, ADMIN_USER, ADMIN_PASS)


def test_each_user_gets_their_own_wardrobe(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Solo")
    token = login(client, un, pw)
    own, wardrobes = own_wardrobe(client, token)
    assert own["my_role"] == "owner"
    assert own["can_edit"] and own["can_manage"]
    # A fresh, un-shared user only sees their own kast.
    assert len(wardrobes) == 1


def test_viewer_can_vote_but_not_edit_and_admin_reaches_everything(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, au, ap = make_user(client, admin, "Alice")
    bob, bu, bp = make_user(client, admin, "Bob")
    alice_t = login(client, au, ap)
    bob_t = login(client, bu, bp)

    alice_w, _ = own_wardrobe(client, alice_t)
    wid = alice_w["id"]

    i1 = add_item(client, alice_t, wid, "Blauw overhemd", "Overhemd", color="blauw", season="Alle seizoenen")
    i2 = add_item(client, alice_t, wid, "Grijze broek", "Broek", color="grijs", season="Alle seizoenen")
    assert i1.status_code == 201 and i2.status_code == 201, (i1.text, i2.text)
    i1_id, i2_id = i1.json()["id"], i2.json()["id"]
    assert i1.json()["wardrobe_id"] == wid

    # Bob has no access yet.
    assert client.get(f"/api/items?wardrobe_id={wid}", headers=h(bob_t)).status_code == 403
    assert client.get(f"/api/items/{i1_id}", headers=h(bob_t)).status_code == 403

    # Alice invites Bob as a viewer.
    r = client.post(f"/api/wardrobes/{wid}/members", headers=h(alice_t), json={"username": bu, "role": "viewer"})
    assert r.status_code == 201, r.text

    # Bob now sees the kast as a read-only viewer.
    bob_wardrobes = client.get("/api/wardrobes", headers=h(bob_t)).json()
    shared = [w for w in bob_wardrobes if w["id"] == wid]
    assert shared and shared[0]["my_role"] == "viewer" and not shared[0]["can_edit"]

    # Viewer can read...
    listing = client.get(f"/api/items?wardrobe_id={wid}", headers=h(bob_t))
    assert listing.status_code == 200 and len(listing.json()) == 2

    # ...cannot add items...
    assert add_item(client, bob_t, wid, "x", "Broek").status_code == 403

    # ...but CAN vote on combinations.
    vote = client.post("/api/matches", headers=h(bob_t), json={"item_a_id": i1_id, "item_b_id": i2_id, "verdict": "yes"})
    assert vote.status_code == 204, vote.text

    # The approval shows up in outfits.
    outfits = client.get(f"/api/matches/outfits/{i1_id}", headers=h(alice_t)).json()
    assert any(p["item"]["id"] == i2_id for p in outfits)

    # Promote Bob to editor -> he can now add.
    r = client.patch(f"/api/wardrobes/{wid}/members/{bob['id']}", headers=h(alice_t), json={"role": "editor"})
    assert r.status_code == 200, r.text
    assert add_item(client, bob_t, wid, "Riem", "Riem").status_code == 201

    # Admin reaches Alice's kast without an invite, with edit rights.
    admin_wardrobes = client.get("/api/wardrobes", headers=h(admin)).json()
    roles = {w["id"]: w["my_role"] for w in admin_wardrobes}
    assert roles.get(wid) == "admin"
    assert add_item(client, admin, wid, "Admin stuk", "Trui").status_code == 201

    # Bob (not owner/admin) cannot manage members.
    assert client.post(f"/api/wardrobes/{wid}/members", headers=h(bob_t), json={"username": ADMIN_USER, "role": "viewer"}).status_code == 403

    # Revoking Bob removes his access.
    assert client.delete(f"/api/wardrobes/{wid}/members/{bob['id']}", headers=h(alice_t)).status_code == 204
    bob_wardrobes = client.get("/api/wardrobes", headers=h(bob_t)).json()
    assert all(w["id"] != wid for w in bob_wardrobes)


def test_items_and_votes_are_scoped_per_wardrobe(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, cu, cp = make_user(client, admin, "Carol")
    carol_t = login(client, cu, cp)
    carol_w, _ = own_wardrobe(client, carol_t)

    add_item(client, carol_t, carol_w["id"], "Enig stuk", "Trui")
    listing = client.get(f"/api/items?wardrobe_id={carol_w['id']}", headers=h(carol_t)).json()
    # Only Carol's own item is visible here, not garments from other test kasten.
    assert [it["name"] for it in listing] == ["Enig stuk"]

    stats = client.get(f"/api/matches/stats?wardrobe_id={carol_w['id']}", headers=h(carol_t)).json()
    assert stats["item_count"] == 1


def test_cannot_invite_unknown_user(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, du, dp = make_user(client, admin, "Dave")
    dave_t = login(client, du, dp)
    dave_w, _ = own_wardrobe(client, dave_t)
    r = client.post(
        f"/api/wardrobes/{dave_w['id']}/members",
        headers=h(dave_t),
        json={"username": "doesnotexist", "role": "viewer"},
    )
    assert r.status_code == 404
