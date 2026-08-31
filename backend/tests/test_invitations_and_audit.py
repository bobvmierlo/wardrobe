"""Invitation links, gated registration and the audit trail."""

import uuid

from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, h, login, make_user, own_wardrobe


def create_invite(client, token, wardrobe_id, role="viewer", label="Partner", days=14):
    r = client.post(
        f"/api/wardrobes/{wardrobe_id}/invitations",
        headers=h(token),
        json={"role": role, "label": label, "expires_days": days},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_stranger_registers_through_the_link_and_lands_in_the_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Eigenaar")
    owner = login(client, ou, op)
    wardrobe, _ = own_wardrobe(client, owner)

    invite = create_invite(client, owner, wardrobe["id"], role="editor", label="nieuw@voorbeeld.nl")
    assert invite["path"] == f"/invite/{invite['token']}"
    assert invite["status"] == "open"

    # The link explains itself without any login at all.
    info = client.get(f"/api/invitations/{invite['token']}")
    assert info.status_code == 200, info.text
    assert info.json()["wardrobe_name"] == wardrobe["name"]
    assert info.json()["role"] == "editor"

    username = "n_" + uuid.uuid4().hex[:10]
    r = client.post(
        f"/api/invitations/{invite['token']}/register",
        json={"username": username, "display_name": "Nieuw", "password": "pw123456"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    newcomer = body["access_token"]
    assert body["user"]["is_admin"] is False

    # They can reach the shared kast as an editor, and own one themselves.
    reachable = client.get("/api/wardrobes", headers=h(newcomer)).json()
    roles = {w["id"]: w["my_role"] for w in reachable}
    assert roles[wardrobe["id"]] == "editor"
    assert any(role == "owner" for role in roles.values())

    # A used link cannot be used again.
    assert client.get(f"/api/invitations/{invite['token']}").status_code == 410
    r = client.post(
        f"/api/invitations/{invite['token']}/register",
        json={"username": "x_" + uuid.uuid4().hex[:8], "display_name": "X", "password": "pw123456"},
    )
    assert r.status_code == 410, r.text


def test_registration_is_closed_without_a_valid_invitation(client):
    # Self-registration is off unless a beheerder opens it…
    r = client.post(
        "/api/auth/register",
        json={"username": "sneak", "display_name": "Sneak", "password": "pw123456"},
    )
    assert r.status_code == 403, r.text
    # …and a made-up token is refused.
    r = client.post(
        "/api/invitations/geen-echte-token/register",
        json={"username": "sneak", "display_name": "Sneak", "password": "pw123456"},
    )
    assert r.status_code == 404, r.text


def test_an_existing_user_accepts_an_invitation(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Deler")
    _, gu, gp = make_user(client, admin, "Gast")
    owner, guest = login(client, ou, op), login(client, gu, gp)
    wardrobe, _ = own_wardrobe(client, owner)

    invite = create_invite(client, owner, wardrobe["id"], role="viewer")
    r = client.post(f"/api/invitations/{invite['token']}/accept", headers=h(guest))
    assert r.status_code == 204, r.text

    reachable = {w["id"]: w["my_role"] for w in client.get("/api/wardrobes", headers=h(guest)).json()}
    assert reachable[wardrobe["id"]] == "viewer"

    listed = client.get(f"/api/wardrobes/{wardrobe['id']}/invitations", headers=h(owner)).json()
    used = next(i for i in listed if i["id"] == invite["id"])
    assert used["status"] == "accepted"
    assert used["accepted_by"]["display_name"] == "Gast"


def test_a_revoked_invitation_stops_working(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Intrekker")
    _, gu, gp = make_user(client, admin, "Afgewezen")
    owner, guest = login(client, ou, op), login(client, gu, gp)
    wardrobe, _ = own_wardrobe(client, owner)

    invite = create_invite(client, owner, wardrobe["id"])
    assert client.delete(f"/api/invitations/{invite['id']}", headers=h(owner)).status_code == 204
    assert client.get(f"/api/invitations/{invite['token']}").status_code == 410
    assert client.post(
        f"/api/invitations/{invite['token']}/accept", headers=h(guest)
    ).status_code == 410


def test_only_the_owner_can_hand_out_links(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Baas")
    _, gu, gp = make_user(client, admin, "Buitenstaander")
    owner, outsider = login(client, ou, op), login(client, gu, gp)
    wardrobe, _ = own_wardrobe(client, owner)

    r = client.post(
        f"/api/wardrobes/{wardrobe['id']}/invitations",
        headers=h(outsider),
        json={"role": "viewer"},
    )
    assert r.status_code == 403, r.text


def test_the_audit_trail_records_who_did_what_and_is_admin_only(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    user, un, pw = make_user(client, admin, "Boekhouder")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)

    data = {"wardrobe_id": str(wardrobe["id"]), "name": "Auditbroek", "category": "Broek"}
    item = client.post("/api/items", headers=h(token), data=data)
    assert item.status_code == 201, item.text

    r = client.get("/api/audit", headers=h(admin), params={"q": "Auditbroek"})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] >= 1
    entry = page["entries"][0]
    assert entry["action"] == "item.create"
    assert entry["action_label"] == "Kledingstuk toegevoegd"
    assert entry["user_name"] == "Boekhouder"
    assert entry["wardrobe_id"] == wardrobe["id"]
    assert "item.create" in page["actions"]

    # A plain user may not read the trail, nor the technical log.
    assert client.get("/api/audit", headers=h(token)).status_code == 403
    assert client.get("/api/logs", headers=h(token)).status_code == 403
    assert client.get("/api/logs", headers=h(admin)).status_code == 200


def test_a_failed_login_is_recorded_without_the_password(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    name = "ghost_" + uuid.uuid4().hex[:8]
    r = client.post("/api/auth/login", data={"username": name, "password": "geheim-wachtwoord"})
    assert r.status_code == 401

    page = client.get(
        "/api/audit", headers=h(admin), params={"action": "auth.login_failed", "q": name}
    ).json()
    assert page["total"] >= 1
    assert name in page["entries"][0]["detail"]
    assert "geheim-wachtwoord" not in page["entries"][0]["detail"]


def test_an_invitation_token_never_reaches_the_log(client):
    """The token is a credential, so it must not be readable in the log screen."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Voorzichtig")
    owner = login(client, ou, op)
    wardrobe, _ = own_wardrobe(client, owner)

    invite = create_invite(client, owner, wardrobe["id"])
    client.get(f"/api/invitations/{invite['token']}")

    logs = client.get("/api/logs", headers=h(admin), params={"limit": 500}).json()
    assert logs, "the request log should not be empty"
    assert all(invite["token"] not in entry["message"] for entry in logs)
    assert any("/api/invitations/<token>" in entry["message"] for entry in logs)
