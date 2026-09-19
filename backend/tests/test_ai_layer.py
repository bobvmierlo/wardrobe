"""De optionele AI-laag.

De dienst wordt nooit echt gebeld: :func:`app.ai._ask` is het enige punt dat
het netwerk op gaat, dus dat wordt hier vervangen — dezelfde opzet als bij het
weer. Wat deze tests vooral vastleggen is de taakverdeling: de regels bepalen
wat mag, het model vult in waar geen regel bestaat, en alles wat terugkomt gaat
alsnog langs de eigen woordenlijsten.
"""

import pytest

from app import ai as ai_layer
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
    _, un, pw = make_user(client, admin, "AI-gebruiker")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    return token, wardrobe["id"]


@pytest.fixture
def ai_on(client):
    """Zet de laag aan zoals een beheerder dat in de app zou doen."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    r = client.put(
        "/api/ai/settings",
        headers=h(admin),
        json={"enabled": True, "api_key": "sk-ant-test-sleutel"},
    )
    assert r.status_code == 200, r.text
    yield r.json()
    client.put("/api/ai/settings", headers=h(admin), json={"enabled": False, "api_key": ""})


def item(client, token, wardrobe_id, name, category, **extra):
    r = add_item(client, token, wardrobe_id, name, category, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def _config(enabled=True, key="sk-ant-test"):
    """Een AI-config zoals app_settings 'm zou opleveren."""
    from app.app_settings import AiConfig

    return AiConfig(
        enabled=enabled, api_key=key, model="claude-opus-5", effort="low",
        timeout_seconds=1.0, refusal_fallback=False,
    )


def answer_with(monkeypatch, payload, record=None):
    """Laat de dienst dit antwoorden, en leg vast wat er heen ging."""
    def fake(config, system, prompt, schema, max_tokens):
        if record is not None:
            record.append({"system": system, "prompt": prompt, "schema": schema})
        return payload

    monkeypatch.setattr(ai_layer, "_ask", fake)


# ---------------------------------------------------------------------------
# Uit, tenzij
# ---------------------------------------------------------------------------

def test_the_layer_is_off_until_a_key_is_configured():
    from app.app_settings import AiConfig

    def config(enabled, key):
        return AiConfig(
            enabled=enabled, api_key=key, model="m", effort="low",
            timeout_seconds=1.0, refusal_fallback=False,
        )

    assert ai_layer.is_configured(config(False, "")) is False
    # Aan zetten zonder sleutel is niet genoeg — anders zou de knop verschijnen
    # en bij de eerste druk pas stuklopen.
    assert ai_layer.is_configured(config(True, "")) is False
    assert ai_layer.is_configured(config(False, "sk-test")) is False
    assert ai_layer.is_configured(config(True, "sk-test")) is True


def test_the_screen_is_told_whether_the_layer_exists(client, kast):
    token, wid = kast
    admin = login(client, ADMIN_USER, ADMIN_PASS)

    r = client.get("/api/autofill/preview", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    assert r.json()["ai_available"] is False

    client.put(
        "/api/ai/settings", headers=h(admin), json={"enabled": True, "api_key": "sk-test"}
    )
    r = client.get("/api/autofill/preview", headers=h(token), params={"wardrobe_id": wid})
    assert r.json()["ai_available"] is True

    client.put("/api/ai/settings", headers=h(admin), json={"enabled": False, "api_key": ""})


def test_asking_for_ai_while_it_is_off_still_runs_the_rules(client, kast):
    token, wid = kast
    item(client, token, wid, "Winterjas", "Jas")

    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tagged"] == 1, "de regels doen gewoon hun werk"
    assert body["by_ai"] == 0
    assert "staat uit" in body["ai_note"]


# ---------------------------------------------------------------------------
# De regels gaan voor
# ---------------------------------------------------------------------------

def test_the_model_is_only_asked_about_what_the_rules_could_not_place(
    client, kast, ai_on, monkeypatch
):
    token, wid = kast
    # De regels weten raad met een winterjas, maar niet met een sieraad.
    coat = item(client, token, wid, "Winterjas", "Jas")
    necklace = item(client, token, wid, "Gouden ketting", "Sieraad")

    sent = []
    answer_with(
        monkeypatch,
        {"items": [{"id": necklace["id"], "occasions": ["Feest"], "weather": []}]},
        record=sent,
    )

    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_ai"] == 1
    assert body["tagged"] == 2  # de jas van de regels, de ketting van het model

    # En de jas is niet eens meegestuurd.
    assert str(necklace["id"]) in sent[0]["prompt"]
    assert "Winterjas" not in sent[0]["prompt"]

    listed = {
        i["name"]: i
        for i in client.get("/api/items", headers=h(token), params={"wardrobe_id": wid}).json()
    }
    assert listed["Winterjas"]["weather_tags"] == ["Koud", "Regen", "Winderig"]
    assert listed["Gouden ketting"]["occasions"] == ["Feest"]


def test_the_model_never_overwrites_what_somebody_already_tagged(
    client, kast, ai_on, monkeypatch
):
    token, wid = kast
    mine = item(client, token, wid, "Gouden ketting", "Sieraad", occasion="Werk", weather="Mild")

    answer_with(
        monkeypatch,
        {"items": [{"id": mine["id"], "occasions": ["Feest"], "weather": ["Heet"]}]},
    )
    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text

    after = client.get(f"/api/items/{mine['id']}", headers=h(token)).json()
    assert after["occasions"] == ["Werk"]
    assert after["weather_tags"] == ["Mild"]


# ---------------------------------------------------------------------------
# Alles wat terugkomt gaat langs de eigen lijsten
# ---------------------------------------------------------------------------

def test_a_tag_this_installation_does_not_know_is_thrown_away(client, kast, ai_on, monkeypatch):
    token, wid = kast
    necklace = item(client, token, wid, "Gouden ketting", "Sieraad")

    answer_with(
        monkeypatch,
        {
            "items": [
                {
                    "id": necklace["id"],
                    "occasions": ["Feest", "Gala", "Bruiloft"],
                    "weather": ["Mild", "Zandstorm"],
                }
            ]
        },
    )
    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text

    after = client.get(f"/api/items/{necklace['id']}", headers=h(token)).json()
    assert after["occasions"] == ["Feest"], "Gala en Bruiloft bestaan hier niet"
    assert after["weather_tags"] == ["Mild"], "Zandstorm is geen weertype van deze app"


def test_a_garment_that_was_never_sent_is_ignored(client, kast, ai_on, monkeypatch):
    """Een id dat wij niet stuurden hoort niet in het antwoord te staan."""
    token, wid = kast
    necklace = item(client, token, wid, "Gouden ketting", "Sieraad")
    other = item(client, token, wid, "Tweede ketting", "Sieraad", occasion="Werk", weather="Mild")

    answer_with(
        monkeypatch,
        {
            "items": [
                {"id": necklace["id"], "occasions": ["Feest"], "weather": []},
                {"id": other["id"], "occasions": ["Sport"], "weather": []},
                {"id": 999999, "occasions": ["Werk"], "weather": []},
            ]
        },
    )
    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text
    assert r.json()["by_ai"] == 1, "alleen het stuk dat echt meeging telt"

    assert client.get(f"/api/items/{other['id']}", headers=h(token)).json()["occasions"] == ["Werk"]


def test_a_broken_answer_costs_the_ai_not_the_button(client, kast, ai_on, monkeypatch):
    token, wid = kast
    item(client, token, wid, "Winterjas", "Jas")
    item(client, token, wid, "Gouden ketting", "Sieraad")

    def boom(config, system, prompt, schema, max_tokens):
        raise ai_layer.AiUnavailable("De AI-dienst antwoordde niet.")

    monkeypatch.setattr(ai_layer, "_ask", boom)

    r = client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tagged"] == 1, "de regels hebben de jas gewoon gedaan"
    assert body["by_ai"] == 0
    assert "antwoordde niet" in body["ai_note"]


def test_only_the_garment_itself_leaves_the_server(client, kast, ai_on, monkeypatch):
    """Geen foto's, geen personen, geen kastnamen — alleen het kledingstuk."""
    token, wid = kast
    created = item(
        client, token, wid, "Gouden ketting", "Sieraad", color="goud", size="One-size"
    )

    sent = []
    answer_with(monkeypatch, {"items": []}, record=sent)
    client.post(
        "/api/autofill/tags", headers=h(token), params={"wardrobe_id": wid, "use_ai": True}
    )

    prompt = sent[0]["prompt"]
    assert "Gouden ketting" in prompt and "goud" in prompt
    for forbidden in ("photo", "thumb", "wardrobe", "created_by", "AI-gebruiker", ".jpg"):
        assert forbidden not in prompt, f"{forbidden} hoort hier niet in te staan"

    # En het beschrijvingsformaat zelf laat niets anders door.
    assert set(ai_layer.describe_item(_Row(created)).keys()) == {
        "id", "naam", "categorie", "kleur", "seizoen",
    }


class _Row:
    """Een kledingstuk zoals de database het teruggeeft, uit de JSON."""

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.category = data["category"]
        self.color = data["color"]
        self.season = data["season"]


# ---------------------------------------------------------------------------
# Looks laten samenstellen — en de oordelen van de bewoners handhaven
# ---------------------------------------------------------------------------

def compose_answer(*outfits):
    """Een antwoord van het model in de vorm die compose_looks verwacht."""
    return {
        "outfits": [
            {
                "naam": name,
                "item_ids": ids,
                "occasions": occasions,
                "weather": weather,
                "reden": "omdat het kan",
            }
            for name, ids, occasions, weather in outfits
        ]
    }


def test_the_ai_composes_looks_and_they_are_saved(client, kast, ai_on, monkeypatch):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    trousers = item(client, token, wid, "Nette broek", "Broek", color="navy")
    shoes = item(client, token, wid, "Bruine schoenen", "Schoenen", color="bruin")

    answer_with(
        monkeypatch,
        compose_answer(
            ("Nette dinsdag", [shirt["id"], trousers["id"], shoes["id"]], ["Werk"], ["Mild"]),
        ),
    )

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 1, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_ai"] == 1
    look = body["created"][0]
    assert look["name"] == "Nette dinsdag"
    assert {i["id"] for i in look["items"]} == {shirt["id"], trousers["id"], shoes["id"]}

    saved = client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid}).json()
    assert [o["name"] for o in saved] == ["Nette dinsdag"]


def test_a_rejected_pair_is_thrown_out_however_the_model_answers(
    client, kast, ai_on, monkeypatch
):
    """De kern: een "nee" van een huisgenoot wint het van elk model."""
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

    # Het model stelt precies die verboden combinatie voor, plus een geldige.
    answer_with(
        monkeypatch,
        compose_answer(
            ("Verboden look", [shirt["id"], trousers["id"]], [], []),
            ("Prima look", [shirt["id"], jeans["id"]], [], []),
        ),
    )

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 2, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    for look in body["created"]:
        ids = {i["id"] for i in look["items"]}
        assert not {shirt["id"], trousers["id"]} <= ids
    assert not any(look["name"] == "Verboden look" for look in body["created"])
    assert any(look["name"] == "Prima look" for look in body["created"])
    assert "afgekeurd" in body["ai_note"], "en het scherm zegt dat het is afgewezen"


def test_the_approved_and_rejected_pairs_are_actually_sent(client, kast, ai_on, monkeypatch):
    """Het model kan er alleen rekening mee houden als het ze krijgt."""
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    trousers = item(client, token, wid, "Nette broek", "Broek", color="navy")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": shirt["id"], "item_b_id": jeans["id"], "verdict": "yes"},
    )
    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": shirt["id"], "item_b_id": trousers["id"], "verdict": "no"},
    )

    sent = []
    answer_with(monkeypatch, {"outfits": []}, record=sent)
    client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 2, "use_ai": True},
    )

    import json as _json

    payload = _json.loads(sent[0]["prompt"])
    assert sorted([shirt["id"], jeans["id"]]) in payload["goedgekeurde_paren"]
    assert sorted([shirt["id"], trousers["id"]]) in payload["afgekeurde_paren"]
    assert "afgekeurd paar mag NOOIT" in sent[0]["system"]


def test_a_look_that_already_exists_is_not_proposed_twice(client, kast, ai_on, monkeypatch):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    existing = client.post(
        "/api/outfits",
        headers=h(token),
        params={"wardrobe_id": wid},
        json={"name": "Bestond al", "item_ids": [shirt["id"], jeans["id"]]},
    )
    assert existing.status_code == 201, existing.text

    answer_with(
        monkeypatch, compose_answer(("Nieuw geprobeerd", [shirt["id"], jeans["id"]], [], []))
    )
    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 1, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_ai"] == 0
    assert "al bestond" in body["ai_note"]

    saved = client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid}).json()
    assert len(saved) == 1, "er is niets dubbels bijgekomen"


def test_unknown_ids_and_half_empty_proposals_are_dropped(client, kast, ai_on, monkeypatch):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    answer_with(
        monkeypatch,
        compose_answer(
            ("Verzonnen kleding", [999998, 999999], [], []),
            ("Eén stuk", [shirt["id"]], [], []),
            ("Deels verzonnen", [shirt["id"], jeans["id"], 999999], [], []),
        ),
    )
    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 3, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    created = r.json()["created"]

    kept = [look for look in created if look["name"] == "Deels verzonnen"]
    assert kept, "de twee echte stukken mogen blijven"
    assert {i["id"] for i in kept[0]["items"]} == {shirt["id"], jeans["id"]}
    assert not any(look["name"] in {"Verzonnen kleding", "Eén stuk"} for look in created)


def test_the_app_tops_up_what_the_ai_did_not_deliver(client, kast, ai_on, monkeypatch):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")
    item(client, token, wid, "Grijze trui", "Trui", color="grijs")
    item(client, token, wid, "Nette broek", "Broek", color="navy")

    answer_with(monkeypatch, compose_answer(("Van de AI", [shirt["id"], jeans["id"]], [], [])))

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 3, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_ai"] == 1
    assert len(body["created"]) > 1, "de app vult zelf aan"

    sets = [frozenset(i["id"] for i in look["items"]) for look in body["created"]]
    assert len(sets) == len(set(sets)), "en dubbelt de look van de AI niet"
    names = [look["name"] for look in body["created"]]
    assert len(names) == len(set(names))


def test_the_model_cannot_tag_a_look_against_its_own_clothes(client, kast, ai_on, monkeypatch):
    token, wid = kast
    coat = item(client, token, wid, "Winterjas", "Jas", color="zwart", weather="Koud")
    trousers = item(client, token, wid, "Wollen broek", "Broek", color="grijs", weather="Koud")

    # Het model beweert dat deze winterkleding voor de hitte is.
    answer_with(
        monkeypatch,
        compose_answer(("Zomers", [coat["id"], trousers["id"]], [], ["Heet", "Koud"])),
    )
    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 1, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    look = r.json()["created"][0]
    assert look["weather_tags"] == ["Koud"], "Heet spreekt de kleding tegen en valt af"


def test_the_model_may_tag_a_look_whose_clothes_say_nothing(client, kast, ai_on, monkeypatch):
    """Precies waar de AI-laag voor bestaat: invullen waar niets staat."""
    token, wid = kast
    a = item(client, token, wid, "Gouden ketting", "Sieraad", color="goud")
    b = item(client, token, wid, "Zwarte jurk", "Jurk", color="zwart")

    answer_with(monkeypatch, compose_answer(("Avondje uit", [a["id"], b["id"]], ["Feest"], ["Mild"])))
    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 1, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    look = r.json()["created"][0]
    assert look["occasions"] == ["Feest"]
    assert look["weather_tags"] == ["Mild"]


def test_an_unreachable_service_leaves_the_app_to_compose(client, kast, ai_on, monkeypatch):
    token, wid = kast
    item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    def boom(config, system, prompt, schema, max_tokens):
        raise ai_layer.AiUnavailable("De AI-dienst antwoordde niet.")

    monkeypatch.setattr(ai_layer, "_ask", boom)

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 2, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_ai"] == 0
    assert body["created"], "de app heeft het zonder gedaan"
    assert "antwoordde niet" in body["ai_note"]


def test_nothing_is_asked_when_there_is_nothing_to_compose(monkeypatch):
    called = []

    def fake(config, system, prompt, schema, max_tokens):
        called.append(prompt)
        return {}

    monkeypatch.setattr(ai_layer, "_ask", fake)
    assert ai_layer.compose_looks(_config(), [], set(), set(), set(), ["Werk"], ["Koud"], 5) == []
    assert called == []
