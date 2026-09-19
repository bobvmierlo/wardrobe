"""De optionele AI-laag.

De dienst wordt nooit echt gebeld: :func:`app.ai._ask` is het enige punt dat
het netwerk op gaat, dus dat wordt hier vervangen — dezelfde opzet als bij het
weer. Wat deze tests vooral vastleggen is de taakverdeling: de regels bepalen
wat mag, het model vult in waar geen regel bestaat, en alles wat terugkomt gaat
alsnog langs de eigen woordenlijsten.
"""

import pytest

from app import ai as ai_layer
from app.config import settings
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
def ai_on(monkeypatch):
    """Doe alsof een beheerder de laag heeft aangezet."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "test-sleutel")
    return settings


def item(client, token, wardrobe_id, name, category, **extra):
    r = add_item(client, token, wardrobe_id, name, category, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def answer_with(monkeypatch, payload, record=None):
    """Laat de dienst dit antwoorden, en leg vast wat er heen ging."""
    def fake(system, prompt, schema, max_tokens):
        if record is not None:
            record.append({"system": system, "prompt": prompt, "schema": schema})
        return payload

    monkeypatch.setattr(ai_layer, "_ask", fake)


# ---------------------------------------------------------------------------
# Uit, tenzij
# ---------------------------------------------------------------------------

def test_the_layer_is_off_until_a_key_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_layer.is_configured() is False

    # Aan zetten zonder sleutel is niet genoeg — anders zou de knop verschijnen
    # en bij de eerste druk pas stuklopen.
    monkeypatch.setattr(settings, "ai_enabled", True)
    assert ai_layer.is_configured() is False

    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    assert ai_layer.is_configured() is True


def test_the_screen_is_told_whether_the_layer_exists(client, kast, monkeypatch):
    token, wid = kast
    monkeypatch.setattr(settings, "ai_enabled", False)
    r = client.get("/api/autofill/preview", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    assert r.json()["ai_available"] is False

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    r = client.get("/api/autofill/preview", headers=h(token), params={"wardrobe_id": wid})
    assert r.json()["ai_available"] is True


def test_asking_for_ai_while_it_is_off_still_runs_the_rules(client, kast, monkeypatch):
    token, wid = kast
    monkeypatch.setattr(settings, "ai_enabled", False)
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

    def boom(system, prompt, schema, max_tokens):
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
# Namen voor looks — en alleen namen
# ---------------------------------------------------------------------------

def test_the_ai_names_looks_but_does_not_choose_the_clothes(client, kast, ai_on, monkeypatch):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    trousers = item(client, token, wid, "Nette broek", "Broek", color="navy")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    # Dit paar is afgekeurd: geen enkele naamgeving mag het terugbrengen.
    r = client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": shirt["id"], "item_b_id": trousers["id"], "verdict": "no"},
    )
    assert r.status_code == 204, r.text

    answer_with(
        monkeypatch,
        {"namen": [{"index": 0, "naam": "Frisse maandag"}, {"index": 1, "naam": "Rustig blauw"}]},
    )

    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 3, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["named_by_ai"] >= 1
    assert any(look["name"] == "Frisse maandag" for look in body["created"])

    for look in body["created"]:
        ids = {i["id"] for i in look["items"]}
        assert not {shirt["id"], trousers["id"]} <= ids, "afgekeurd paar blijft afgekeurd"
    assert any(
        {shirt["id"], jeans["id"]} <= {i["id"] for i in look["items"]}
        for look in body["created"]
    )


def test_a_name_that_clashes_or_is_empty_falls_back_to_the_apps_own(
    client, kast, ai_on, monkeypatch
):
    token, wid = kast
    shirt = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    jeans = item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    # Een bestaande look bezet de naam die het model wil gebruiken.
    existing = client.post(
        "/api/outfits",
        headers=h(token),
        params={"wardrobe_id": wid},
        json={"name": "Frisse maandag", "item_ids": [shirt["id"]]},
    )
    assert existing.status_code == 201, existing.text

    answer_with(monkeypatch, {"namen": [{"index": 0, "naam": "  frisse maandag "}]})
    r = client.post(
        "/api/autofill/looks",
        headers=h(token),
        params={"wardrobe_id": wid, "count": 1, "use_ai": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["named_by_ai"] == 0
    for look in body["created"]:
        assert look["name"] != "Frisse maandag"
        assert look["name"]


def test_names_are_trimmed_and_deduplicated_before_they_are_used(monkeypatch):
    """De opschoning zelf, los van een kast."""
    class _Item:
        id, name, category, color, season = 1, "Trui", "Trui", "grijs", ""

    looks = [[_Item()], [_Item()], [_Item()], [_Item()]]
    answer_with(
        monkeypatch,
        {
            "namen": [
                {"index": 0, "naam": "  Zachte   zondag \n"},
                {"index": 1, "naam": "zachte zondag"},   # dubbel, valt af
                {"index": 2, "naam": "   "},             # leeg, valt af
                {"index": 9, "naam": "Bestaat niet"},    # index buiten bereik
                {"index": 3, "naam": "x" * 200},         # wordt afgekapt
            ]
        },
    )
    names = ai_layer.name_looks(looks)
    assert names[0] == "Zachte zondag"
    assert 1 not in names and 2 not in names and 9 not in names
    assert len(names[3]) == ai_layer.MAX_NAME


def test_nothing_is_sent_when_there_is_nothing_to_ask(monkeypatch):
    called = []

    def fake(system, prompt, schema, max_tokens):
        called.append(prompt)
        return {}

    monkeypatch.setattr(ai_layer, "_ask", fake)
    assert ai_layer.suggest_tags([], ["Werk"], ["Koud"]) == []
    assert ai_layer.name_looks([]) == {}
    assert called == [], "een lege vraag hoort de deur niet uit te gaan"
