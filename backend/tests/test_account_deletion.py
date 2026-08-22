"""Deleting an account must actually delete it — and only it.

The bug these cover: ``db.delete(user)`` removed one row and orphaned the
rest, so the username stayed taken, the kast lived on, and (because SQLite
reuses a freed row id) the next account created inherited the departed
person's wardrobe.
"""

import uuid

from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, add_item, h, login, make_user, own_wardrobe


def make_account(client, admin, display="Weg"):
    """A user with a kast, two garments, a verdict, a skip and an invitation."""
    user, un, pw = make_user(client, admin, display)
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    wid = wardrobe["id"]
    a = add_item(client, token, wid, "Trui", "Trui", season="Alle seizoenen").json()["id"]
    b = add_item(client, token, wid, "Broek", "Broek", season="Alle seizoenen").json()["id"]
    c = add_item(client, token, wid, "Jeans", "Jeans", season="Alle seizoenen").json()["id"]
    client.post("/api/matches", headers=h(token),
                json={"item_a_id": a, "item_b_id": b, "verdict": "yes"})
    client.post("/api/matches/skip", headers=h(token),
                json={"item_a_id": a, "item_b_id": c})
    client.post(f"/api/wardrobes/{wid}/invitations", headers=h(token),
                json={"role": "viewer", "label": "vriend"})
    return user, un, pw, token, wid, [a, b, c]


def test_deleting_an_account_frees_the_username_and_removes_the_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    user, un, pw, token, wid, items = make_account(client, admin)

    assert client.delete(f"/api/users/{user['id']}", headers=h(admin)).status_code == 204

    # The account is gone from every angle the app can look.
    assert un not in [u["username"] for u in client.get("/api/users", headers=h(admin)).json()]
    assert client.post("/api/auth/login", data={"username": un, "password": pw}).status_code == 401
    # Their kast and garments went with them.
    assert client.get(f"/api/items/{items[0]}", headers=h(admin)).status_code == 404
    assert client.get("/api/wardrobes", headers=h(admin)).status_code == 200
    assert wid not in [w["id"] for w in client.get("/api/wardrobes", headers=h(admin)).json()]

    # And the username is free again — the symptom that started all this.
    again = client.post(
        "/api/users", headers=h(admin),
        json={"username": un, "display_name": "Opnieuw", "password": "pw123456", "is_admin": False},
    )
    assert again.status_code == 201, again.text


def test_a_recreated_account_never_inherits_the_old_wardrobe(client):
    """SQLite hands the freed row id to the next account; the kast must not follow."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    user, un, pw, token, wid, items = make_account(client, admin, "Vertrokken")

    client.delete(f"/api/users/{user['id']}", headers=h(admin))
    r = client.post(
        "/api/users", headers=h(admin),
        json={"username": un, "display_name": "Nieuw", "password": "pw123456", "is_admin": False},
    )
    assert r.status_code == 201
    fresh = login(client, un, "pw123456")

    own, reachable = own_wardrobe(client, fresh)
    # Whatever id it was given, the kast must be empty and theirs alone.
    assert client.get(f"/api/items?wardrobe_id={own['id']}", headers=h(fresh)).json() == []
    assert len(reachable) == 1, "a fresh account sees only its own kast"
    assert client.get(
        "/api/matches/stats", headers=h(fresh), params={"wardrobe_id": own["id"]}
    ).json()["judged_by_me"] == 0


def test_garments_added_to_someone_elses_kast_survive_the_deletion(client):
    """Deleting a helper must not take another household's clothes with them."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    owner_user, ou, op = make_user(client, admin, "Eigenaar")
    helper_user, hu, hp = make_user(client, admin, "Helper")
    owner, helper = login(client, ou, op), login(client, hu, hp)
    owner_w, _ = own_wardrobe(client, owner)

    client.post(f"/api/wardrobes/{owner_w['id']}/members", headers=h(owner),
                json={"username": hu, "role": "editor"})
    gift = add_item(client, helper, owner_w["id"], "Jas van de helper", "Jas").json()["id"]

    assert client.delete(f"/api/users/{helper_user['id']}", headers=h(admin)).status_code == 204

    kept = client.get(f"/api/items/{gift}", headers=h(owner))
    assert kept.status_code == 200, "the owner keeps the garment"
    assert kept.json()["name"] == "Jas van de helper"
    # Their access to the kast is revoked, though.
    assert [m["user"]["username"] for m in
            client.get(f"/api/wardrobes/{owner_w['id']}/members", headers=h(owner)).json()] == []


def test_the_audit_trail_outlives_the_account(client):
    """"Wie heeft dit gedaan?" must stay answerable after the account is gone."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    name = "Boekhouder " + uuid.uuid4().hex[:6]
    user, un, pw, token, wid, items = make_account(client, admin, name)

    client.delete(f"/api/users/{user['id']}", headers=h(admin))

    page = client.get("/api/audit", headers=h(admin), params={"q": "Trui", "limit": 200}).json()
    theirs = [e for e in page["entries"] if e["user_name"] == name]
    assert theirs, "their actions are still in the trail, under their name"
    assert all(e["user_id"] is None for e in theirs), "only the broken link is dropped"

    deletion = client.get(
        "/api/audit", headers=h(admin), params={"action": "user.delete", "q": un}
    ).json()
    assert deletion["total"] >= 1
    assert "kledingstuk" in deletion["entries"][0]["detail"]


def test_deleting_an_account_leaves_other_accounts_untouched(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    doomed, un, pw, token, wid, items = make_account(client, admin, "Doomed")
    keeper_user, ku, kp = make_user(client, admin, "Blijft")
    keeper = login(client, ku, kp)
    keeper_w, _ = own_wardrobe(client, keeper)
    k1 = add_item(client, keeper, keeper_w["id"], "Polo", "Polo", season="Alle seizoenen").json()["id"]
    k2 = add_item(client, keeper, keeper_w["id"], "Chino", "Chino", season="Alle seizoenen").json()["id"]
    client.post("/api/matches", headers=h(keeper),
                json={"item_a_id": k1, "item_b_id": k2, "verdict": "yes"})

    client.delete(f"/api/users/{doomed['id']}", headers=h(admin))

    assert len(client.get(f"/api/items?wardrobe_id={keeper_w['id']}", headers=h(keeper)).json()) == 2
    assert [p["item"]["id"] for p in
            client.get(f"/api/matches/outfits/{k1}", headers=h(keeper)).json()] == [k2]
