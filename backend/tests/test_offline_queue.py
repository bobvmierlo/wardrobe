"""The pair queue the app carries offline.

The swipe screen used to ask the server for one pair at a time, which is fine
until the connection drops. It now takes a stretch of the queue in hand. These
tests pin down that the stretch is the *same* queue: whatever someone swipes
through on the train is what the server would have handed them one by one.
"""

from tests.test_combining import next_pair, setup_wardrobe
from tests.test_wardrobes import h


def queue(client, token, wardrobe_id, anchor_id=None, limit=None):
    params = {"wardrobe_id": wardrobe_id}
    if anchor_id is not None:
        params["anchor_id"] = anchor_id
    if limit is not None:
        params["limit"] = limit
    r = client.get("/api/matches/next/queue", headers=h(token), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def key(pair):
    return frozenset((pair["anchor"]["id"], pair["candidate"]["id"]))


def test_the_queue_starts_with_exactly_what_next_offers(client):
    token, wid, _ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Broek", "Broek", "blauw"),
        ("Trui", "Trui", "grijs"),
        ("Schoenen", "Schoenen", "bruin"),
    )
    head = next_pair(client, token, wid)
    batch = queue(client, token, wid)
    assert batch, "de wachtrij mag niet leeg zijn"
    assert key(batch[0]) == key(head)
    # Every pair is offered once, however many anchors it ranks under.
    keys = [key(p) for p in batch]
    assert len(keys) == len(set(keys))


def test_the_queue_respects_the_limit_and_an_anchor(client):
    token, wid, ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Broek", "Broek", "blauw"),
        ("Trui", "Trui", "grijs"),
        ("Schoenen", "Schoenen", "bruin"),
    )
    assert len(queue(client, token, wid, limit=2)) == 2
    # A silly limit is clamped rather than refused.
    assert len(queue(client, token, wid, limit=0)) == 1
    assert len(queue(client, token, wid, limit=5000)) <= 100

    anchored = queue(client, token, wid, anchor_id=ids[0])
    assert anchored
    assert all(p["anchor"]["id"] == ids[0] for p in anchored)


def test_judged_pairs_leave_the_queue(client):
    token, wid, _ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Broek", "Broek", "blauw"),
        ("Trui", "Trui", "grijs"),
    )
    before = queue(client, token, wid)
    first = before[0]
    r = client.post(
        "/api/matches",
        headers=h(token),
        json={
            "item_a_id": first["anchor"]["id"],
            "item_b_id": first["candidate"]["id"],
            "verdict": "yes",
        },
    )
    assert r.status_code == 204, r.text

    after = queue(client, token, wid)
    assert key(first) not in {key(p) for p in after}
    assert len(after) == len(before) - 1


def test_a_skipped_pair_sinks_to_the_back(client):
    token, wid, _ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Broek", "Broek", "blauw"),
        ("Trui", "Trui", "grijs"),
    )
    first = queue(client, token, wid)[0]
    r = client.post(
        "/api/matches/skip",
        headers=h(token),
        json={"item_a_id": first["anchor"]["id"], "item_b_id": first["candidate"]["id"]},
    )
    assert r.status_code == 204, r.text

    after = queue(client, token, wid)
    assert key(after[-1]) == key(first)
    assert after[-1]["skipped"] is True


def skip(client, token, pair):
    r = client.post(
        "/api/matches/skip",
        headers=h(token),
        json={"item_a_id": pair["anchor"]["id"], "item_b_id": pair["candidate"]["id"]},
    )
    assert r.status_code == 204, r.text


def test_a_skipped_pair_sinks_behind_the_pairs_of_every_other_garment(client):
    """Skipping is "not now", not "not this garment".

    A pair put off used to sink only to the bottom of the candidates of the
    garment it was found under, so it came back while other garments still had
    pairs nobody had ever seen. It now goes behind the whole queue.
    """
    token, wid, _ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Trui", "Trui", "grijs"),
        ("Broek", "Broek", "blauw"),
        ("Rok", "Rok", "zwart"),
    )
    before = queue(client, token, wid)
    assert len(before) == 4, before
    first = before[0]
    skip(client, token, first)

    after = queue(client, token, wid)
    assert key(after[-1]) == key(first)
    assert after[-1]["skipped"] is True
    # Everything ahead of it is still unseen, including the pairs that share a
    # garment with the one that was put off.
    assert all(p["skipped"] is False for p in after[:-1])
    assert {key(p) for p in after} == {key(p) for p in before}


def test_pairs_put_off_come_back_in_the_order_they_were_skipped(client):
    token, wid, _ids = setup_wardrobe(
        client,
        ("Overhemd", "Overhemd", "wit"),
        ("Trui", "Trui", "grijs"),
        ("Broek", "Broek", "blauw"),
        ("Rok", "Rok", "zwart"),
    )
    first, second = queue(client, token, wid)[:2]
    skip(client, token, first)
    skip(client, token, second)

    tail = queue(client, token, wid)[-2:]
    assert [key(p) for p in tail] == [key(first), key(second)]

    # Skipping the longest-postponed pair again sends it to the very back.
    skip(client, token, first)
    tail = queue(client, token, wid)[-2:]
    assert [key(p) for p in tail] == [key(second), key(first)]


def test_the_queue_needs_access_to_the_wardrobe(client):
    from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, login, make_user

    token, wid, _ids = setup_wardrobe(
        client, ("Overhemd", "Overhemd", "wit"), ("Broek", "Broek", "blauw")
    )
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Buitenstaander")
    outsider = login(client, un, pw)
    r = client.get(
        "/api/matches/next/queue", headers=h(outsider), params={"wardrobe_id": wid}
    )
    assert r.status_code == 403
