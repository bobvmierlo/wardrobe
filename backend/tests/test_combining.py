"""Skipping, undoing and accepting combinations.

These exercise the swipe queue from the outside: what the app offers next
after a skip, what disappears after an undo, and when a system suggestion may
be turned into a real combination.
"""

from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, add_item, h, login, make_user, own_wardrobe


def setup_wardrobe(client, *items):
    """A fresh user with a wardrobe holding the given (name, category, colour)."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Swiper")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    ids = []
    for name, category, color in items:
        r = add_item(
            client, token, wardrobe["id"], name, category,
            color=color, season="Alle seizoenen",
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return token, wardrobe["id"], ids


def next_pair(client, token, wardrobe_id, anchor_id=None):
    params = {"wardrobe_id": wardrobe_id}
    if anchor_id is not None:
        params["anchor_id"] = anchor_id
    r = client.get("/api/matches/next", headers=h(token), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_skipping_sends_a_pair_to_the_back_of_the_queue(client):
    token, wid, (top, bottom_a, bottom_b) = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Broek A", "Broek", "navy"),
        ("Broek B", "Broek", "grijs"),
    )

    first = next_pair(client, token, wid, top)
    assert first is not None and first["skipped"] is False
    skipped_id = first["candidate"]["id"]

    r = client.post(
        "/api/matches/skip",
        headers=h(token),
        json={"item_a_id": top, "item_b_id": skipped_id},
    )
    assert r.status_code == 204, r.text

    # The other, never-seen candidate is offered before the skipped one.
    second = next_pair(client, token, wid, top)
    assert second["candidate"]["id"] != skipped_id
    assert second["skipped"] is False

    # Judge that one; now only the skipped pair is left and it comes back.
    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": top, "item_b_id": second["candidate"]["id"], "verdict": "yes"},
    )
    third = next_pair(client, token, wid, top)
    assert third["candidate"]["id"] == skipped_id
    assert third["skipped"] is True

    stats = client.get("/api/matches/stats", headers=h(token), params={"wardrobe_id": wid})
    assert stats.json()["skipped_by_me"] == 1
    assert skipped_id in {bottom_a, bottom_b}


def test_skipping_an_already_judged_pair_is_refused(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Trui", "Trui", "grijs"), ("Jeans", "Jeans", "denim")
    )
    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "yes"},
    )
    r = client.post(
        "/api/matches/skip", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom},
    )
    assert r.status_code == 409, r.text


def test_a_verdict_can_be_undone_and_the_pair_returns(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Polo", "Polo", "wit"), ("Chino", "Chino", "beige")
    )
    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "yes"},
    )
    assert len(client.get(f"/api/matches/outfits/{top}", headers=h(token)).json()) == 1
    # Nothing left to swipe once the only pair is judged.
    assert next_pair(client, token, wid) is None

    judged = client.get(
        "/api/matches/judged", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    assert len(judged) == 1
    assert judged[0]["my_verdict"] == "yes"
    assert [v["verdict"] for v in judged[0]["votes"]] == ["yes"]

    r = client.delete(f"/api/matches/{top}/{bottom}", headers=h(token))
    assert r.status_code == 204, r.text
    assert client.get(f"/api/matches/outfits/{top}", headers=h(token)).json() == []
    back = next_pair(client, token, wid)
    assert back is not None and back["skipped"] is False
    assert client.get(
        "/api/matches/judged", headers=h(token), params={"wardrobe_id": wid}
    ).json() == []


def test_undoing_a_skipped_pair_makes_it_unseen_again(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Blouse", "Blouse", "wit"), ("Rok", "Rok", "zwart")
    )
    client.post(
        "/api/matches/skip", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom},
    )
    assert next_pair(client, token, wid)["skipped"] is True
    client.post(
        "/api/matches", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "no"},
    )
    client.delete(f"/api/matches/{top}/{bottom}", headers=h(token))
    assert next_pair(client, token, wid)["skipped"] is False


def test_a_suggestion_can_be_accepted_once_and_then_disappears(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Wit overhemd", "Overhemd", "wit"), ("Navy broek", "Broek", "navy")
    )
    suggestions = client.get(
        "/api/matches/suggestions", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    assert suggestions, "a white top and navy trousers should be suggested"
    ids = [it["id"] for it in suggestions[0]["items"]]
    assert suggestions[0]["already_combined"] is False

    r = client.post("/api/matches/suggestions/accept", headers=h(token), json={"item_ids": ids})
    assert r.status_code == 204, r.text

    # It is a real combination now...
    partners = client.get(f"/api/matches/outfits/{top}", headers=h(token)).json()
    assert [p["item"]["id"] for p in partners] == [bottom]
    # ...so it is no longer offered as a suggestion, and cannot be accepted twice.
    again = client.get(
        "/api/matches/suggestions", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    assert all(sorted(it["id"] for it in s["items"]) != sorted(ids) for s in again)
    r = client.post("/api/matches/suggestions/accept", headers=h(token), json={"item_ids": ids})
    assert r.status_code == 409, r.text


def test_a_rejected_pair_is_never_suggested_or_acceptable(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Groene trui", "Trui", "groen"), ("Oranje broek", "Broek", "oranje")
    )
    client.post(
        "/api/matches", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "no"},
    )
    suggestions = client.get(
        "/api/matches/suggestions", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    assert all({top, bottom} - {it["id"] for it in s["items"]} for s in suggestions)

    r = client.post(
        "/api/matches/suggestions/accept", headers=h(token), json={"item_ids": [top, bottom]}
    )
    assert r.status_code == 409, r.text


def test_accepting_a_suggestion_needs_access_to_the_wardrobe(client):
    token, wid, ids = setup_wardrobe(
        client, ("Hoodie", "Hoodie", "zwart"), ("Broek", "Broek", "grijs")
    )
    other_token, _, _ = setup_wardrobe(client, ("Vest", "Vest", "beige"))
    r = client.post(
        "/api/matches/suggestions/accept", headers=h(other_token), json={"item_ids": ids}
    )
    assert r.status_code == 403, r.text


def share_with_partner(client, owner_token, wardrobe_id, role="viewer"):
    """Add a second person to the wardrobe; returns their token and display name."""
    from tests.test_wardrobes import make_user

    admin = login(client, ADMIN_USER, ADMIN_PASS)
    user, un, pw = make_user(client, admin, "Partner")
    r = client.post(
        f"/api/wardrobes/{wardrobe_id}/members",
        headers=h(owner_token),
        json={"username": un, "role": role},
    )
    assert r.status_code == 201, r.text
    return login(client, un, pw), user["display_name"]


def test_a_rejected_pair_is_listed_on_the_garment_with_who_said_no(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Rode trui", "Trui", "rood"), ("Roze broek", "Broek", "roze")
    )
    partner, partner_name = share_with_partner(client, token, wid)

    client.post(
        "/api/matches", headers=h(partner),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "no"},
    )

    rejected = client.get(f"/api/matches/rejected/{top}", headers=h(token)).json()
    assert len(rejected) == 1
    assert rejected[0]["item"]["id"] == bottom
    assert rejected[0]["rejected_by"] == [partner_name]
    assert rejected[0]["approved_by"] == []
    # It was the partner's "nee", not mine, so it is not mine to undo.
    assert rejected[0]["rejected_by_me"] is False

    # It stays out of the approved list — a rejection is not an outfit.
    assert client.get(f"/api/matches/outfits/{top}", headers=h(token)).json() == []
    # And it reads the same from the other garment's page.
    assert client.get(f"/api/matches/rejected/{bottom}", headers=h(token)).json()[0][
        "item"
    ]["id"] == top


def test_a_split_vote_shows_both_sides(client):
    """The case that is otherwise baffling: I said yes, my partner said no."""
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Groene polo", "Polo", "groen"), ("Oranje broek", "Broek", "oranje")
    )
    partner, partner_name = share_with_partner(client, token, wid)

    client.post(
        "/api/matches", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "yes"},
    )
    client.post(
        "/api/matches", headers=h(partner),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "no"},
    )

    rejected = client.get(f"/api/matches/rejected/{top}", headers=h(token)).json()
    assert len(rejected) == 1
    assert rejected[0]["rejected_by"] == [partner_name]
    assert rejected[0]["approved_by"] == ["Swiper"]
    assert rejected[0]["rejected_by_me"] is False
    # Blocked, so it is nowhere near the Outfits screen.
    assert client.get(f"/api/matches/outfits/{top}", headers=h(token)).json() == []

    # From the partner's side the "nee" is theirs, and theirs to withdraw.
    theirs = client.get(f"/api/matches/rejected/{top}", headers=h(partner)).json()
    assert theirs[0]["rejected_by_me"] is True
    assert client.delete(f"/api/matches/{top}/{bottom}", headers=h(partner)).status_code == 204
    assert client.get(f"/api/matches/rejected/{top}", headers=h(token)).json() == []
    # With the block gone, my own "ja" makes it a real combination.
    assert [p["item"]["id"] for p in
            client.get(f"/api/matches/outfits/{top}", headers=h(token)).json()] == [bottom]


def test_the_rejected_list_respects_wardrobe_access(client):
    token, wid, (top, bottom) = setup_wardrobe(
        client, ("Blauwe trui", "Trui", "blauw"), ("Bruine broek", "Broek", "bruin")
    )
    client.post(
        "/api/matches", headers=h(token),
        json={"item_a_id": top, "item_b_id": bottom, "verdict": "no"},
    )
    outsider, _, _ = setup_wardrobe(client, ("Losse jas", "Jas", "grijs"))
    assert client.get(f"/api/matches/rejected/{top}", headers=h(outsider)).status_code == 403
    assert client.get("/api/matches/rejected/999999", headers=h(token)).status_code == 404
