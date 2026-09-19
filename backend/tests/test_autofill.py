"""Aanvullen: guessing tags, and composing looks out of an existing kast.

The point of both is a wardrobe somebody has been using for a year without ever
tagging anything. So these tests care most about what it refuses to do: never
overwrite, never invent an occasion the installation does not have, never
repeat a look that already exists.
"""

import pytest

from tests.test_wardrobes import (
    ADMIN_PASS,
    ADMIN_USER,
    add_item,
    h,
    login,
    make_user,
    own_wardrobe,
)


@pytest.fixture
def kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Aanvuller")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    return token, wardrobe["id"]


def item(client, token, wardrobe_id, name, category, **extra):
    r = add_item(client, token, wardrobe_id, name, category, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def stocked(client, token, wid):
    """A small kast with nothing tagged, the way a real one arrives here."""
    return [
        item(client, token, wid, "Winterjas", "Jas", color="zwart"),
        item(client, token, wid, "Wit overhemd", "Overhemd", color="wit"),
        item(client, token, wid, "Nette broek", "Broek", color="navy"),
        item(client, token, wid, "Blauwe jeans", "Jeans", color="denim"),
        item(client, token, wid, "Grijze hoodie", "Hoodie", color="grijs"),
        item(client, token, wid, "Korte broek", "Shorts", color="beige"),
    ]


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

def test_tags_are_guessed_from_what_the_garment_is(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    r = client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    assert r.json()["tagged"] >= 5

    listed = client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    by_name = {i["name"]: i for i in listed}
    assert by_name["Winterjas"]["weather_tags"] == ["Koud", "Regen", "Winderig"]
    assert by_name["Korte broek"]["weather_tags"] == ["Warm", "Heet", "Zonnig"]
    assert by_name["Grijze hoodie"]["weather_tags"] == ["Koud", "Mild"]
    # The occasion table is deliberately much shorter than the weather one.
    assert by_name["Wit overhemd"]["occasions"] == ["Werk", "Casual"]
    assert by_name["Grijze hoodie"]["occasions"] == ["Casual", "Weekend"]


def test_a_season_fills_in_where_the_category_says_nothing(client, kast):
    token, wid = kast
    item(client, token, wid, "Zomerrok", "Rok", season="Zomer")
    item(client, token, wid, "Winterrok", "Rok", season="Winter")

    client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})
    by_name = {
        i["name"]: i
        for i in client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    }
    assert by_name["Zomerrok"]["weather_tags"] == ["Warm", "Heet"]
    assert by_name["Winterrok"]["weather_tags"] == ["Koud"]


def test_what_somebody_already_tagged_is_never_touched(client, kast):
    token, wid = kast
    mine = item(client, token, wid, "Winterjas", "Jas", weather="Zonnig", occasion="Feest")
    untouched = item(client, token, wid, "Tweede jas", "Jas")

    r = client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200
    assert r.json()["tagged"] == 1, "alleen het ongetagde stuk telt mee"

    after = client.get(f"/api/items/{mine['id']}", headers=h(token)).json()
    assert after["weather_tags"] == ["Zonnig"], "een eigen keuze blijft staan"
    assert after["occasions"] == ["Feest"]
    assert client.get(f"/api/items/{untouched['id']}", headers=h(token)).json()["weather_tags"]


def test_an_occasion_the_installation_does_not_have_is_not_invented(client, kast):
    """A beheerder who deleted "Formeel" must not get it back on every blazer."""
    token, wid = kast
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    occasions = client.get("/api/occasions", headers=h(admin)).json()
    formeel = next(o for o in occasions if o["name"] == "Formeel")
    assert client.delete(f"/api/occasions/{formeel['id']}", headers=h(admin)).status_code == 204

    blazer = item(client, token, wid, "Blauwe blazer", "Blazer")
    client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})

    after = client.get(f"/api/items/{blazer['id']}", headers=h(token)).json()
    assert after["occasions"] == ["Werk"], "Formeel bestaat niet meer en komt niet terug"

    # Put it back for the tests that come after this one.
    client.post("/api/occasions", headers=h(admin), json={"name": "Formeel"})


def test_a_dry_run_changes_nothing_but_says_what_it_would_do(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "dry_run": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tagged"] >= 5
    assert body["examples"] and body["examples"][0]["weather"]

    listed = client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    assert all(not i["weather_tags"] for i in listed), "een proefdraai schrijft niets weg"


def test_a_viewer_may_not_tag_somebody_elses_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Eigenaar")
    _, gu, gp = make_user(client, admin, "Kijker")
    owner, guest = login(client, ou, op), login(client, gu, gp)
    wardrobe, _ = own_wardrobe(client, owner)
    client.post(
        f"/api/wardrobes/{wardrobe['id']}/members",
        headers=h(owner),
        json={"username": gu, "role": "viewer"},
    )
    item(client, owner, wardrobe["id"], "Jas", "Jas")

    r = client.post(
        "/api/autofill/tags", headers=h(guest), params={"wardrobe_id": wardrobe["id"]}
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Composing looks
# ---------------------------------------------------------------------------

def test_looks_are_composed_and_saved_with_the_tags_their_clothes_agree_on(client, kast):
    token, wid = kast
    stocked(client, token, wid)
    client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})

    r = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 3}
    )
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert created, "een kast met zes stuks moet iets op kunnen leveren"

    for look in created:
        assert len(look["items"]) >= 2
        # The name says what it is rather than "Look 3".
        assert look["name"] and not look["name"].lower().startswith("look ")

    saved = client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid}).json()
    assert len(saved) == len(created)


def test_a_look_only_claims_weather_all_of_its_clothes_agree_on(client, kast):
    token, wid = kast
    # A coat for the cold and shorts for the heat can be combined by colour, but
    # the look that results is for neither: the tags must not claim otherwise.
    item(client, token, wid, "Winterjas", "Jas", color="zwart", weather="Koud")
    item(client, token, wid, "Wollen trui", "Trui", color="grijs", weather="Koud,Mild")
    item(client, token, wid, "Nette broek", "Broek", color="navy", weather="Koud,Mild")

    r = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 2}
    )
    assert r.status_code == 200, r.text
    for look in r.json()["created"]:
        tagged = [i for i in look["items"] if i["weather_tags"]]
        if len(tagged) > 1:
            # Whatever it claims, every tagged garment in it must agree.
            for tag in look["weather_tags"]:
                assert all(tag in i["weather_tags"] for i in tagged)


def test_running_it_twice_does_not_produce_the_same_looks(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    first = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 3}
    ).json()["created"]
    second = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 3}
    ).json()["created"]

    def sets(looks):
        return {frozenset(i["id"] for i in look["items"]) for look in looks}

    assert not (sets(first) & sets(second)), "dezelfde combinatie mag niet terugkomen"
    names = [look["name"] for look in first + second]
    assert len(names) == len(set(names)), "en de namen moeten uniek blijven"


def test_composed_looks_are_varied_rather_than_the_same_top_six_times(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    created = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 3}
    ).json()["created"]

    if len(created) >= 2:
        first = {i["id"] for i in created[0]["items"]}
        second = {i["id"] for i in created[1]["items"]}
        overlap = len(first & second) / len(first)
        assert overlap <= 0.5, "twee looks mogen niet vrijwel hetzelfde zijn"


def test_a_pair_somebody_rejected_never_ends_up_in_a_composed_look(client, kast):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    trousers = item(client, token, wid, "Nette broek", "Broek", color="navy")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    r = client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": shirt["id"], "item_b_id": trousers["id"], "verdict": "no"},
    )
    assert r.status_code == 204, r.text

    created = client.post(
        "/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid, "count": 6}
    ).json()["created"]

    for look in created:
        ids = {i["id"] for i in look["items"]}
        assert not {shirt["id"], trousers["id"]} <= ids
    assert any(
        {shirt["id"], jeans["id"]} <= {i["id"] for i in look["items"]} for look in created
    ), "de combinatie die niemand afkeurde mag er wél zijn"


def test_an_empty_kast_says_so_instead_of_failing(client, kast):
    token, wid = kast
    r = client.post("/api/autofill/looks", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == []
    assert "te weinig" in body["note"]


def test_the_preview_says_what_both_buttons_would_do(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    r = client.get("/api/autofill/preview", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_count"] == 6
    assert body["without_weather"] == 6
    assert body["taggable"] >= 5
    assert body["outfit_count"] == 0
    assert body["composable"] >= 1

    # And it really did change nothing.
    listed = client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    assert all(not i["weather_tags"] for i in listed)
    assert client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid}).json() == []


def test_a_dry_run_of_the_composer_saves_nothing(client, kast):
    token, wid = kast
    stocked(client, token, wid)

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 3, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == []
    assert body["proposed"], "een proefdraai moet wel laten zien wat er zou komen"
    assert all(len(p["items"]) >= 2 for p in body["proposed"])

    assert client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid}).json() == []


def test_the_name_prefers_the_more_specific_rule(client, kast):
    """"Regenjas" must meet the rain row, not the plain "jas" row below it."""
    token, wid = kast
    plain = item(client, token, wid, "Nette jas", "Jas")
    rain = item(client, token, wid, "Regenjas", "Jas")

    client.post("/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid})
    by_id = {
        i["id"]: i
        for i in client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    }
    assert by_id[plain["id"]]["weather_tags"] == ["Koud", "Winderig"]
    assert by_id[rain["id"]]["weather_tags"] == ["Koud", "Regen", "Winderig"]
