"""The front door: self-registration and account invitations.

Two ways for someone without an account to get one, and both are a beheerder's
call: the toggle that opens self-registration for everyone, and the one-time
account link that lets in exactly one person while the door stays shut.
"""

import uuid

from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, h, login, make_user


def new_name() -> str:
    return "n_" + uuid.uuid4().hex[:10]


def set_self_registration(client, admin_token: str, open_: bool):
    r = client.put(
        "/api/auth/config", headers=h(admin_token), json={"self_registration": open_}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_login_screen_is_told_the_door_is_shut(client):
    r = client.get("/api/auth/config")
    assert r.status_code == 200, r.text
    assert r.json() == {"self_registration": False}


def test_a_beheerder_opens_and_closes_self_registration(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    username = new_name()
    try:
        set_self_registration(client, admin, True)
        assert client.get("/api/auth/config").json()["self_registration"] is True

        r = client.post(
            "/api/auth/register",
            json={"username": username, "display_name": "Zelf", "password": "pw123456"},
        )
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]
        assert r.json()["user"]["is_admin"] is False

        # A newcomer starts with a kast of their own and nothing else.
        mine = client.get("/api/wardrobes", headers=h(token)).json()
        assert [w["my_role"] for w in mine] == ["owner"]

        # The username is taken now, and says so instead of 500-ing.
        r = client.post(
            "/api/auth/register",
            json={"username": username, "display_name": "Zelf", "password": "pw123456"},
        )
        assert r.status_code == 409, r.text
    finally:
        set_self_registration(client, admin, False)

    # Shut again: the same request that just worked is refused.
    r = client.post(
        "/api/auth/register",
        json={"username": new_name(), "display_name": "Te laat", "password": "pw123456"},
    )
    assert r.status_code == 403, r.text


def test_only_a_beheerder_may_flip_the_toggle(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Gewone gebruiker")
    user = login(client, un, pw)

    assert client.put(
        "/api/auth/config", headers=h(user), json={"self_registration": True}
    ).status_code == 403
    assert client.put(
        "/api/auth/config", json={"self_registration": True}
    ).status_code == 401
    # Still shut.
    assert client.get("/api/auth/config").json()["self_registration"] is False


def test_an_account_invitation_lets_one_newcomer_in(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    r = client.post(
        "/api/invitations/account",
        headers=h(admin),
        json={"label": "Buurman", "expires_days": 14},
    )
    assert r.status_code == 201, r.text
    invite = r.json()
    assert invite["kind"] == "account"
    assert invite["wardrobe_name"] is None
    assert invite["role"] is None
    assert invite["path"] == f"/invite/{invite['token']}"

    # The link explains itself without a login, and gives nothing else away.
    info = client.get(f"/api/invitations/{invite['token']}")
    assert info.status_code == 200, info.text
    assert info.json()["kind"] == "account"
    assert info.json()["wardrobe_name"] is None

    username = new_name()
    r = client.post(
        f"/api/invitations/{invite['token']}/register",
        json={"username": username, "display_name": "Buurman", "password": "pw123456"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]

    # They own a kast and share none — an account link hands out no access.
    mine = client.get("/api/wardrobes", headers=h(token)).json()
    assert [w["my_role"] for w in mine] == ["owner"]

    # One-time, like every invitation.
    assert client.get(f"/api/invitations/{invite['token']}").status_code == 410
    listed = client.get("/api/invitations/account", headers=h(admin)).json()
    used = next(i for i in listed if i["id"] == invite["id"])
    assert used["status"] == "accepted"
    assert used["accepted_by"]["display_name"] == "Buurman"


def test_an_account_invitation_has_nothing_for_someone_who_already_has_an_account(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Al binnen")
    user = login(client, un, pw)

    invite = client.post(
        "/api/invitations/account", headers=h(admin), json={"label": "Niemand"}
    ).json()
    r = client.post(f"/api/invitations/{invite['token']}/accept", headers=h(user))
    assert r.status_code == 400, r.text
    # And the link is still there for the person it was meant for.
    assert client.get(f"/api/invitations/{invite['token']}").json()["status"] == "open"


def test_account_invitations_are_a_beheerder_matter(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Nieuwsgierig")
    user = login(client, un, pw)

    assert client.post(
        "/api/invitations/account", headers=h(user), json={"label": "Ik"}
    ).status_code == 403
    assert client.get("/api/invitations/account", headers=h(user)).status_code == 403

    invite = client.post(
        "/api/invitations/account", headers=h(admin), json={"label": "Van de beheerder"}
    ).json()
    assert client.delete(
        f"/api/invitations/{invite['id']}", headers=h(user)
    ).status_code == 403
    assert client.delete(
        f"/api/invitations/{invite['id']}", headers=h(admin)
    ).status_code == 204
    assert client.get(f"/api/invitations/{invite['token']}").status_code == 410


def test_the_account_list_is_not_mistaken_for_a_token(client):
    """"/api/invitations/account" is a route, not somebody's invitation."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    r = client.get("/api/invitations/account", headers=h(admin))
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    assert all(i["kind"] == "account" for i in r.json())
