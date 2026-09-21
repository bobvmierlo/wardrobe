"""Outfits, the weather behind them, and everything built on top.

The weather services are never actually called: :func:`app.weather._get_json`
is the single door out to the internet, so the tests replace it and hand back
the shape Open-Meteo and Zippopotam really answer with.
"""

import pytest

from app import weather as weather_service
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
    """A fresh user with their own kast and a handful of tagged garments."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Outfitter")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    return token, wardrobe["id"]


def item(client, token, wardrobe_id, name, category, **extra):
    r = add_item(client, token, wardrobe_id, name, category, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def make_outfit(client, token, wardrobe_id, name, item_ids, **tags):
    body = {"name": name, "item_ids": item_ids}
    body.update(tags)
    r = client.post(
        "/api/outfits", headers=h(token), params={"wardrobe_id": wardrobe_id}, json=body
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Turning a forecast into wardrobe tags
# ---------------------------------------------------------------------------

def test_weather_codes_become_the_tags_garments_carry():
    assert weather_service.tags_for(0, 22.0, 5.0) == ["Zonnig", "Warm"]
    assert weather_service.tags_for(63, 6.0, 10.0) == ["Regen", "Koud"]
    assert weather_service.tags_for(73, -2.0, 40.0) == ["Sneeuw", "Koud", "Winderig"]
    assert weather_service.tags_for(3, 30.0, 0.0) == ["Bewolkt", "Heet"]


def test_temperature_bands_use_what_it_feels_like():
    # 7° in the wind is a coat; the band is read off the apparent temperature.
    assert weather_service.temperature_tag(7.9) == "Koud"
    assert weather_service.temperature_tag(8.0) == "Mild"
    assert weather_service.temperature_tag(17.9) == "Mild"
    assert weather_service.temperature_tag(18.0) == "Warm"
    assert weather_service.temperature_tag(26.0) == "Heet"


def test_an_unknown_weather_code_still_answers_something():
    tags = weather_service.tags_for(12345, 12.0, 0.0)
    assert tags == ["Bewolkt", "Mild"]


# ---------------------------------------------------------------------------
# Looking a place up
# ---------------------------------------------------------------------------

def test_a_dutch_postcode_goes_to_pdok(client, kast, monkeypatch):
    """Het eigen land van deze app hoort te werken.

    Dit liep op Zippopotam, dat geen Nederlandse postcodes heeft: elke "5421
    AB" werd een 404, viel door naar de naamzoeker, en die maakt van vier
    cijfers niets. Je eigen postcode intypen leverde dus gewoon geen resultaat.
    """
    token, _ = kast
    calls = []

    def fake(url, params):
        calls.append((url, params))
        return {
            "response": {
                "docs": [
                    {
                        "type": "postcode",
                        "weergavenaam": "5421 AB Gemert",
                        "postcode": "5421AB",
                        "woonplaatsnaam": "Gemert",
                        "provincienaam": "Noord-Brabant",
                        "centroide_ll": "POINT(5.6889 51.5583)",
                    },
                    # Dezelfde plaats nog eens: een postcode heeft vaak tien
                    # straten, en dat zijn geen tien keuzes voor een mens.
                    {
                        "type": "postcode",
                        "postcode": "5421AC",
                        "woonplaatsnaam": "Gemert",
                        "provincienaam": "Noord-Brabant",
                        "centroide_ll": "POINT(5.6901 51.5590)",
                    },
                ]
            }
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "5421 AB"})
    assert r.status_code == 200, r.text
    results = r.json()
    assert len(results) == 1, "één plaats, niet één per straat"
    assert results[0]["name"] == "Gemert"
    assert results[0]["label"] == "Gemert, Noord-Brabant"
    assert results[0]["postcode"] == "5421AB"
    # POINT() zet de lengtegraad voorop; omgekeerd lees je komt in zee uit.
    assert results[0]["latitude"] == pytest.approx(51.5583)
    assert results[0]["longitude"] == pytest.approx(5.6889)

    url, params = calls[0]
    assert "pdok" in url
    assert params["q"] == "5421 AB"
    assert "zippopotam" not in url


def test_the_four_digits_on_their_own_are_enough(client, kast, monkeypatch):
    token, _ = kast
    asked = []

    def fake(url, params):
        asked.append(params.get("q"))
        return {
            "response": {
                "docs": [
                    {
                        "postcode": "5421AA",
                        "woonplaatsnaam": "Gemert",
                        "provincienaam": "Noord-Brabant",
                        "centroide_ll": "POINT(5.6889 51.5583)",
                    }
                ]
            }
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "5421"})
    assert r.status_code == 200, r.text
    assert r.json()[0]["name"] == "Gemert"
    assert asked == ["5421"]


def test_a_postcode_elsewhere_still_goes_to_zippopotam(client, kast, monkeypatch):
    """Zippopotam is prima voor de landen die het wél heeft."""
    token, _ = kast
    calls = []
    monkeypatch.setattr(weather_service.settings, "weather_country", "us")

    def fake(url, params):
        calls.append(url)
        return {
            "post code": "90210",
            "country": "United States",
            "places": [
                {
                    "place name": "Beverly Hills",
                    "latitude": "34.0901",
                    "longitude": "-118.4065",
                    "state": "California",
                }
            ],
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "9021"})
    assert r.status_code == 200, r.text
    assert r.json()[0]["name"] == "Beverly Hills"
    assert calls and calls[0].endswith("/us/9021")


def test_a_place_name_goes_to_the_geocoder(client, kast, monkeypatch):
    token, _ = kast

    def fake(url, params):
        assert params.get("name") == "Utrecht"
        return {
            "results": [
                {
                    "name": "Utrecht",
                    "latitude": 52.09,
                    "longitude": 5.12,
                    "admin1": "Utrecht",
                    "country": "Nederland",
                }
            ]
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "Utrecht"})
    assert r.status_code == 200, r.text
    assert r.json()[0]["latitude"] == pytest.approx(52.09)


def test_an_unknown_postcode_falls_through_to_the_name_search(client, kast, monkeypatch):
    token, _ = kast
    seen = []

    def fake(url, params):
        seen.append(url)
        if "pdok" in url:
            raise weather_service.WeatherUnavailable("404")
        return {"results": [{"name": "9999", "latitude": 1.0, "longitude": 2.0}]}

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "9999"})
    assert r.status_code == 200, r.text
    assert len(seen) == 2  # postcode first, then the geocoder
    assert r.json()[0]["name"] == "9999"


def test_a_broken_weather_service_is_a_503_not_a_crash(client, kast, monkeypatch):
    token, _ = kast

    def fake(url, params):
        raise weather_service.WeatherUnavailable("De weerdienst is nu niet bereikbaar")

    monkeypatch.setattr(weather_service, "_get_json", fake)
    r = client.get("/api/weather/search", headers=h(token), params={"q": "Utrecht"})
    assert r.status_code == 503
    assert "niet bereikbaar" in r.json()["detail"]


def test_the_forecast_is_fetched_once_and_then_cached(client, kast, monkeypatch):
    token, _ = kast
    weather_service.clear_cache()
    calls = []

    def fake(url, params):
        calls.append(params)
        return {
            "current": {
                "temperature_2m": 4.0,
                "apparent_temperature": 1.0,
                "precipitation": 0.4,
                "weather_code": 61,
                "wind_speed_10m": 35.0,
                "is_day": 1,
            },
            "daily": {
                "temperature_2m_max": [6.0],
                "temperature_2m_min": [1.0],
                "precipitation_probability_max": [80],
                "weather_code": [61],
            },
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    params = {"latitude": 51.56, "longitude": 5.69}
    first = client.get("/api/weather/current", headers=h(token), params=params)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["tags"] == ["Regen", "Koud", "Winderig"]
    assert body["description"] == "Lichte regen"
    assert body["precipitation_chance"] == 80

    second = client.get("/api/weather/current", headers=h(token), params=params)
    assert second.status_code == 200
    assert len(calls) == 1, "a second look at the same spot must not refetch"
    weather_service.clear_cache()


# ---------------------------------------------------------------------------
# Per-user preferences
# ---------------------------------------------------------------------------

def test_preferences_start_at_the_defaults_and_can_be_changed(client, kast):
    token, _ = kast
    r = client.get("/api/me/preferences", headers=h(token))
    assert r.status_code == 200, r.text
    prefs = r.json()
    assert prefs["wear_log_enabled"] is False, "the wear log is opt-in"
    assert prefs["theme"] == "midnight"
    assert prefs["location_label"] is None

    r = client.put(
        "/api/me/preferences",
        headers=h(token),
        json={
            "theme": "warmzand",
            "wear_log_enabled": True,
            "location_label": "Gemert",
            "latitude": 51.56,
            "longitude": 5.69,
        },
    )
    assert r.status_code == 200, r.text
    prefs = r.json()
    assert prefs["theme"] == "warmzand"
    assert prefs["wear_log_enabled"] is True
    assert prefs["location_label"] == "Gemert"


def test_clearing_the_location_clears_its_coordinates_too(client, kast):
    token, _ = kast
    client.put(
        "/api/me/preferences",
        headers=h(token),
        json={"location_label": "Gemert", "latitude": 51.56, "longitude": 5.69},
    )
    r = client.put("/api/me/preferences", headers=h(token), json={"location_label": ""})
    assert r.status_code == 200, r.text
    prefs = r.json()
    assert prefs["location_label"] is None
    assert prefs["latitude"] is None and prefs["longitude"] is None


def test_preferences_are_private_to_each_account(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, au, ap = make_user(client, admin, "Ann")
    _, bu, bp = make_user(client, admin, "Ben")
    ann, ben = login(client, au, ap), login(client, bu, bp)

    client.put("/api/me/preferences", headers=h(ann), json={"theme": "bos"})
    assert client.get("/api/me/preferences", headers=h(ben)).json()["theme"] == "midnight"


# ---------------------------------------------------------------------------
# Outfits
# ---------------------------------------------------------------------------

def test_an_outfit_keeps_its_garments_and_its_tags(client, kast):
    token, wid = kast
    top = item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    bottom = item(client, token, wid, "Nette broek", "Broek", color="navy")

    outfit = make_outfit(
        client, token, wid, "Nette dinsdag", [top["id"], bottom["id"]],
        occasions=["Werk"], weather_tags=["Mild", "Bewolkt"], seasons=["Herfst"],
        style_tags=["Zakelijk"],
    )
    assert [i["id"] for i in outfit["items"]] == [top["id"], bottom["id"]]
    assert outfit["occasions"] == ["Werk"]
    assert outfit["weather_tags"] == ["Mild", "Bewolkt"]
    assert outfit["wear_count"] == 0

    listed = client.get("/api/outfits", headers=h(token), params={"wardrobe_id": wid})
    assert listed.status_code == 200
    assert [o["id"] for o in listed.json()] == [outfit["id"]]


def test_an_outfit_cannot_reach_into_someone_elses_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, au, ap = make_user(client, admin, "Ann")
    _, bu, bp = make_user(client, admin, "Ben")
    ann, ben = login(client, au, ap), login(client, bu, bp)
    ann_kast, _ = own_wardrobe(client, ann)
    ben_kast, _ = own_wardrobe(client, ben)

    mine = item(client, ann, ann_kast["id"], "Mijn trui", "Trui")
    theirs = item(client, ben, ben_kast["id"], "Hun trui", "Trui")

    r = client.post(
        "/api/outfits",
        headers=h(ann),
        params={"wardrobe_id": ann_kast["id"]},
        json={"name": "Gemengd", "item_ids": [mine["id"], theirs["id"]]},
    )
    assert r.status_code == 400
    assert "dezelfde kast" in r.json()["detail"]


def test_editing_an_outfit_replaces_its_garments(client, kast):
    token, wid = kast
    a = item(client, token, wid, "Trui A", "Trui")
    b = item(client, token, wid, "Trui B", "Trui")
    outfit = make_outfit(client, token, wid, "Eerst A", [a["id"]])

    r = client.put(
        f"/api/outfits/{outfit['id']}",
        headers=h(token),
        json={"name": "Nu B", "item_ids": [b["id"]], "occasions": ["Casual"]},
    )
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == [b["id"]]
    assert r.json()["name"] == "Nu B"


def test_deleting_an_outfit_leaves_the_garments_alone(client, kast):
    token, wid = kast
    top = item(client, token, wid, "Blijft", "Trui")
    outfit = make_outfit(client, token, wid, "Weg", [top["id"]])

    assert client.delete(f"/api/outfits/{outfit['id']}", headers=h(token)).status_code == 204
    assert client.get(f"/api/items/{top['id']}", headers=h(token)).status_code == 200


# ---------------------------------------------------------------------------
# The wear log, which is off until you ask for it
# ---------------------------------------------------------------------------

def test_the_wear_log_refuses_to_record_anything_until_it_is_switched_on(client, kast):
    token, wid = kast
    top = item(client, token, wid, "Trui", "Trui")
    outfit = make_outfit(client, token, wid, "Zondag", [top["id"]])

    r = client.post(f"/api/outfits/{outfit['id']}/wear", headers=h(token), json={})
    assert r.status_code == 409
    assert "draaglogboek" in r.json()["detail"].lower()

    client.put("/api/me/preferences", headers=h(token), json={"wear_log_enabled": True})
    r = client.post(
        f"/api/outfits/{outfit['id']}/wear", headers=h(token), json={"worn_on": "2026-03-01"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["worn_on"] == "2026-03-01"


def test_wearing_the_same_outfit_twice_on_one_day_is_one_entry(client, kast):
    token, wid = kast
    client.put("/api/me/preferences", headers=h(token), json={"wear_log_enabled": True})
    top = item(client, token, wid, "Trui", "Trui")
    outfit = make_outfit(client, token, wid, "Dubbel", [top["id"]])

    for _ in range(2):
        client.post(
            f"/api/outfits/{outfit['id']}/wear", headers=h(token), json={"worn_on": "2026-03-02"}
        )
    history = client.get(f"/api/outfits/{outfit['id']}/wear", headers=h(token))
    assert history.json() == ["2026-03-02"]

    r = client.delete(f"/api/outfits/{outfit['id']}/wear/2026-03-02", headers=h(token))
    assert r.status_code == 204
    assert client.get(f"/api/outfits/{outfit['id']}/wear", headers=h(token)).json() == []


def test_one_persons_wear_log_is_invisible_to_the_other(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    owner, ou, op = make_user(client, admin, "Eigenaar")
    _, gu, gp = make_user(client, admin, "Gast")
    owner_token, guest_token = login(client, ou, op), login(client, gu, gp)
    kast, _ = own_wardrobe(client, owner_token)

    r = client.post(
        f"/api/wardrobes/{kast['id']}/members",
        headers=h(owner_token),
        json={"username": gu, "role": "viewer"},
    )
    assert r.status_code in (200, 201), r.text

    top = item(client, owner_token, kast["id"], "Gedeelde trui", "Trui")
    outfit = make_outfit(client, owner_token, kast["id"], "Gedeeld", [top["id"]])

    for token in (owner_token, guest_token):
        client.put("/api/me/preferences", headers=h(token), json={"wear_log_enabled": True})
    client.post(
        f"/api/outfits/{outfit['id']}/wear", headers=h(owner_token), json={"worn_on": "2026-03-03"}
    )

    assert client.get(f"/api/outfits/{outfit['id']}/wear", headers=h(owner_token)).json() == [
        "2026-03-03"
    ]
    assert client.get(f"/api/outfits/{outfit['id']}/wear", headers=h(guest_token)).json() == []


# ---------------------------------------------------------------------------
# "Je zou dit aan kunnen trekken"
# ---------------------------------------------------------------------------

def set_manual_weather(client, token, tags):
    r = client.put(
        "/api/me/preferences",
        headers=h(token),
        json={"weather_mode": "manual", "manual_weather": tags},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_cold_day_recommends_the_winter_outfit_over_the_summer_one(client, kast):
    token, wid = kast
    set_manual_weather(client, token, ["Koud", "Regen"])

    coat = item(client, token, wid, "Winterjas", "Jas", color="navy")
    jeans = item(client, token, wid, "Jeans", "Jeans", color="denim")
    shorts = item(client, token, wid, "Korte broek", "Shorts", color="beige")
    tee = item(client, token, wid, "T-shirt", "T-shirt", color="wit")

    winter = make_outfit(
        client, token, wid, "Winterlook", [coat["id"], jeans["id"]],
        weather_tags=["Koud", "Regen"], occasions=["Casual"],
    )
    make_outfit(
        client, token, wid, "Zomerlook", [tee["id"], shorts["id"]],
        weather_tags=["Heet", "Zonnig"], occasions=["Casual"],
    )

    r = client.get(
        "/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid}
    )
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["weather"]["tags"] == ["Koud", "Regen"]
    assert "jas" in page["advice"].lower() or "nat" in page["advice"].lower()

    saved = [rec for rec in page["recommendations"] if rec["source"] == "saved"]
    assert saved[0]["outfit_name"] == "Winterlook"
    assert saved[0]["score"] > saved[-1]["score"]
    assert "koud" in saved[0]["reason"].lower()
    assert saved[0]["outfit_id"] == winter["id"]


def test_asking_for_an_occasion_pushes_the_wrong_one_down(client, kast):
    token, wid = kast
    set_manual_weather(client, token, ["Mild", "Bewolkt"])

    shirt = item(client, token, wid, "Overhemd", "Overhemd", color="wit")
    trousers = item(client, token, wid, "Pantalon", "Broek", color="navy")
    hoodie = item(client, token, wid, "Hoodie", "Hoodie", color="grijs")
    joggers = item(client, token, wid, "Joggingbroek", "Broek", color="zwart")

    make_outfit(
        client, token, wid, "Sjiek uit eten", [shirt["id"], trousers["id"]],
        occasions=["Uit eten", "Formeel"], weather_tags=["Mild"],
    )
    make_outfit(
        client, token, wid, "Bankhangen", [hoodie["id"], joggers["id"]],
        occasions=["Casual"], weather_tags=["Mild"],
    )

    r = client.get(
        "/api/outfits/recommendations",
        headers=h(token),
        params={"wardrobe_id": wid, "occasion": "Uit eten"},
    )
    assert r.status_code == 200, r.text
    saved = [rec for rec in r.json()["recommendations"] if rec["source"] == "saved"]
    assert saved[0]["outfit_name"] == "Sjiek uit eten"
    assert "uit eten" in saved[0]["reason"].lower()


def test_what_you_wore_today_is_not_suggested_again_today(client, kast):
    token, wid = kast
    set_manual_weather(client, token, ["Mild", "Bewolkt"])
    client.put("/api/me/preferences", headers=h(token), json={"wear_log_enabled": True})

    a = item(client, token, wid, "Trui A", "Trui", color="grijs")
    b = item(client, token, wid, "Trui B", "Trui", color="navy")
    broek = item(client, token, wid, "Broek", "Broek", color="zwart")

    worn = make_outfit(client, token, wid, "Al gedragen", [a["id"], broek["id"]],
                       weather_tags=["Mild"])
    make_outfit(client, token, wid, "Nog niet", [b["id"], broek["id"]], weather_tags=["Mild"])

    from datetime import date

    client.post(
        f"/api/outfits/{worn['id']}/wear",
        headers=h(token),
        json={"worn_on": date.today().isoformat()},
    )

    r = client.get("/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid})
    saved = [rec for rec in r.json()["recommendations"] if rec["source"] == "saved"]
    assert saved[0]["outfit_name"] == "Nog niet"
    assert saved[-1]["outfit_name"] == "Al gedragen"


def test_an_empty_kast_says_so_instead_of_showing_nothing(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Leeg")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)

    r = client.get(
        "/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wardrobe["id"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["empty_reason"] == "Er zit nog niets in deze kast."


def test_recommendations_fall_back_to_fresh_combinations(client, kast):
    """A kast with garments but no saved outfits still answers the question."""
    token, wid = kast
    set_manual_weather(client, token, ["Mild", "Bewolkt"])
    item(client, token, wid, "Overhemd", "Overhemd", color="wit", season="Alle seizoenen")
    item(client, token, wid, "Broek", "Broek", color="navy", season="Alle seizoenen")

    r = client.get("/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    recs = r.json()["recommendations"]
    assert recs and all(rec["source"] == "new" for rec in recs)
    assert len(recs[0]["items"]) >= 2


# ---------------------------------------------------------------------------
# Ontdekken
# ---------------------------------------------------------------------------

def test_discover_only_builds_from_garments_tagged_for_the_occasion(client, kast):
    token, wid = kast
    item(client, token, wid, "Net overhemd", "Overhemd", color="wit", occasion="Werk")
    item(client, token, wid, "Nette broek", "Broek", color="navy", occasion="Werk")
    item(client, token, wid, "Sportshirt", "T-shirt", color="rood", occasion="Sport")
    item(client, token, wid, "Sportbroek", "Broek", color="zwart", occasion="Sport")

    r = client.get(
        "/api/outfits/discover",
        headers=h(token),
        params={"wardrobe_id": wid, "occasion": "Werk"},
    )
    assert r.status_code == 200, r.text
    suggestions = r.json()
    assert suggestions
    for suggestion in suggestions:
        names = {i["name"] for i in suggestion["items"]}
        assert not (names & {"Sportshirt", "Sportbroek"})


def test_discover_leaves_the_coat_at_home_when_it_is_warm(client, kast):
    token, wid = kast
    item(client, token, wid, "T-shirt", "T-shirt", color="wit", weather="Warm,Heet")
    item(client, token, wid, "Korte broek", "Shorts", color="beige", weather="Warm,Heet")
    item(client, token, wid, "Winterjas", "Jas", color="zwart", weather="Koud")

    r = client.get(
        "/api/outfits/discover",
        headers=h(token),
        params={"wardrobe_id": wid, "weather": "Warm,Zonnig"},
    )
    assert r.status_code == 200, r.text
    for suggestion in r.json():
        assert "Winterjas" not in {i["name"] for i in suggestion["items"]}


def test_discover_keeps_suggesting_after_the_whole_kast_is_swiped(client, kast):
    """The bug: a kast everybody swiped through offered nothing at all.

    The swipe screen drops a combination once it is approved — it is done with
    it. Ontdekken must do the opposite: an approved combination is the best
    answer to "wat kan ik aan", not a disqualified one.
    """
    token, wid = kast
    tops = [
        item(client, token, wid, "Wit overhemd", "Overhemd", color="wit"),
        item(client, token, wid, "Blauwe polo", "Polo", color="blauw"),
    ]
    bottoms = [
        item(client, token, wid, "Navy chino", "Chino", color="navy"),
        item(client, token, wid, "Jeans", "Jeans", color="denim"),
    ]

    before = client.get("/api/outfits/discover", headers=h(token), params={"wardrobe_id": wid})
    assert len(before.json()) == 4

    for top in tops:
        for bottom in bottoms:
            r = client.post(
                "/api/matches",
                headers=h(token),
                json={"item_a_id": top["id"], "item_b_id": bottom["id"], "verdict": "yes"},
            )
            assert r.status_code == 204, r.text

    after = client.get("/api/outfits/discover", headers=h(token), params={"wardrobe_id": wid})
    assert len(after.json()) == 4, "Ontdekken liet alles vallen wat al goedgekeurd was"
    reasons = [x["reason"] for x in after.json()]
    assert all("al goedgekeurde combinatie" in r.lower() for r in reasons), reasons

    # The swipe screen, meanwhile, is rightly finished: nothing left to judge.
    left = client.get("/api/matches/suggestions", headers=h(token), params={"wardrobe_id": wid})
    assert left.json() == []


def test_discover_still_never_builds_a_rejected_pair(client, kast):
    token, wid = kast
    top = item(client, token, wid, "Rode trui", "Trui", color="rood")
    item(client, token, wid, "Navy chino", "Chino", color="navy")
    bad = item(client, token, wid, "Roze broek", "Broek", color="roze")
    client.post(
        "/api/matches",
        headers=h(token),
        json={"item_a_id": top["id"], "item_b_id": bad["id"], "verdict": "no"},
    )

    r = client.get("/api/outfits/discover", headers=h(token), params={"wardrobe_id": wid})
    combos = [{i["name"] for i in s["items"]} for s in r.json()]
    assert {"Rode trui", "Navy chino"} in combos
    assert {"Rode trui", "Roze broek"} not in combos


def test_recommendations_do_not_offer_a_saved_look_twice(client, kast):
    """A saved look is listed once, as "saved" — never again as a new idea."""
    token, wid = kast
    set_manual_weather(client, token, ["Mild", "Bewolkt"])
    top = item(client, token, wid, "Overhemd", "Overhemd", color="wit", season="Alle seizoenen")
    bottom = item(client, token, wid, "Broek", "Broek", color="navy", season="Alle seizoenen")
    make_outfit(client, token, wid, "Mijn look", [top["id"], bottom["id"]])

    r = client.get("/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid})
    recs = r.json()["recommendations"]
    combos = [frozenset(i["id"] for i in rec["items"]) for rec in recs]
    assert len(combos) == len(set(combos)), recs
    mine = frozenset({top["id"], bottom["id"]})
    assert [rec["source"] for rec, c in zip(recs, combos) if c == mine] == ["saved"]


# ---------------------------------------------------------------------------
# Week planner
# ---------------------------------------------------------------------------

def test_the_week_planner_holds_an_outfit_per_day_and_can_clear_it(client, kast):
    token, wid = kast
    top = item(client, token, wid, "Trui", "Trui")
    outfit = make_outfit(client, token, wid, "Maandaglook", [top["id"]])

    r = client.put(
        "/api/planner",
        headers=h(token),
        params={"wardrobe_id": wid},
        json={"day": "2026-03-02", "outfit_id": outfit["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["outfit"]["name"] == "Maandaglook"

    week = client.get(
        "/api/planner/week", headers=h(token), params={"wardrobe_id": wid, "start": "2026-03-04"}
    )
    assert week.status_code == 200, week.text
    body = week.json()
    assert body["start"] == "2026-03-02", "a week starts on its Monday"
    assert len(body["days"]) == 7
    planned = [d for d in body["days"] if d["outfit"]]
    assert len(planned) == 1 and planned[0]["day"] == "2026-03-02"

    cleared = client.put(
        "/api/planner",
        headers=h(token),
        params={"wardrobe_id": wid},
        json={"day": "2026-03-02", "outfit_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["outfit"] is None


def test_a_plan_is_personal_even_in_a_shared_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Eigenaar")
    _, gu, gp = make_user(client, admin, "Gast")
    owner, guest = login(client, ou, op), login(client, gu, gp)
    kast, _ = own_wardrobe(client, owner)
    client.post(
        f"/api/wardrobes/{kast['id']}/members",
        headers=h(owner),
        json={"username": gu, "role": "viewer"},
    )
    top = item(client, owner, kast["id"], "Trui", "Trui")
    outfit = make_outfit(client, owner, kast["id"], "Look", [top["id"]])

    client.put(
        "/api/planner",
        headers=h(owner),
        params={"wardrobe_id": kast["id"]},
        json={"day": "2026-03-05", "outfit_id": outfit["id"]},
    )
    week = client.get(
        "/api/planner/week",
        headers=h(guest),
        params={"wardrobe_id": kast["id"], "start": "2026-03-05"},
    )
    assert week.status_code == 200
    assert all(d["outfit"] is None for d in week.json()["days"])


# ---------------------------------------------------------------------------
# Reistas
# ---------------------------------------------------------------------------

def test_a_packing_list_counts_a_shared_garment_once(client, kast):
    token, wid = kast
    jeans = item(client, token, wid, "Jeans", "Jeans")
    shirt_a = item(client, token, wid, "Shirt A", "T-shirt")
    shirt_b = item(client, token, wid, "Shirt B", "T-shirt")
    day = make_outfit(client, token, wid, "Dag 1", [jeans["id"], shirt_a["id"]])
    evening = make_outfit(client, token, wid, "Dag 2", [jeans["id"], shirt_b["id"]])

    trip = client.post(
        "/api/trips",
        headers=h(token),
        params={"wardrobe_id": wid},
        json={"name": "Weekend Parijs", "destination": "Parijs"},
    )
    assert trip.status_code == 201, trip.text
    trip_id = trip.json()["id"]

    for outfit in (day, evening):
        r = client.post(
            f"/api/trips/{trip_id}/outfits", headers=h(token), json={"outfit_id": outfit["id"]}
        )
        assert r.status_code == 200, r.text
    detail = r.json()

    assert detail["outfit_count"] == 2
    assert detail["item_count"] == 3, "the jeans are packed once, not twice"
    jeans_entry = next(e for e in detail["packing"] if e["item"]["id"] == jeans["id"])
    assert jeans_entry["used_in"] == 2
    assert detail["packing"][0]["item"]["id"] == jeans["id"], "most-needed first"

    packed = client.post(
        f"/api/trips/{trip_id}/packed", headers=h(token), json={"item_id": jeans["id"], "packed": True}
    )
    assert packed.status_code == 200
    assert packed.json()["packed_count"] == 1


def test_removing_an_outfit_shortens_the_packing_list(client, kast):
    token, wid = kast
    a = item(client, token, wid, "Jurk", "Jurk")
    b = item(client, token, wid, "Rok", "Rok")
    one = make_outfit(client, token, wid, "Een", [a["id"]])
    two = make_outfit(client, token, wid, "Twee", [b["id"]])
    trip_id = client.post(
        "/api/trips", headers=h(token), params={"wardrobe_id": wid}, json={"name": "Reis"}
    ).json()["id"]
    for outfit in (one, two):
        client.post(f"/api/trips/{trip_id}/outfits", headers=h(token), json={"outfit_id": outfit["id"]})

    r = client.delete(f"/api/trips/{trip_id}/outfits/{two['id']}", headers=h(token))
    assert r.status_code == 200, r.text
    assert r.json()["item_count"] == 1


# ---------------------------------------------------------------------------
# Inzichten & stijlgids
# ---------------------------------------------------------------------------

def test_insights_count_the_kast_and_name_what_is_never_used(client, kast):
    token, wid = kast
    used = item(client, token, wid, "Wordt gedragen", "Trui", color="navy")
    unused = item(client, token, wid, "Ligt te wachten", "Rok", color="rood")
    make_outfit(client, token, wid, "Look", [used["id"]], occasions=["Werk"])

    r = client.get("/api/insights", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_count"] == 2
    assert body["outfit_count"] == 1
    assert [i["id"] for i in body["unused_items"]] == [unused["id"]]
    assert {e["color"] for e in body["palette"]} == {"navy", "rood"}
    assert body["wear_log_enabled"] is False


def test_the_style_guide_reads_the_installations_own_colour_rules(client, kast):
    token, wid = kast
    item(client, token, wid, "Navy blazer", "Blazer", color="navy")
    item(client, token, wid, "Beige broek", "Broek", color="beige")

    r = client.get("/api/me/style-guide", headers=h(token), params={"wardrobe_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    colors = {c["color"]: c for c in body["colors"]}
    assert set(colors) == {"navy", "beige"}
    # Both are neutrals, so the guide says so rather than listing pairs.
    assert "neutrale" in colors["navy"]["goes_with"][0]
    assert body["uncovered_weather"], "nothing is tagged for weather yet"
    assert any("gelegenheid" in gap["title"] for gap in body["gaps"])


def test_style_dna_is_saved_and_only_accepts_colours_the_engine_knows(client, kast):
    token, _ = kast
    r = client.put(
        "/api/me/style",
        headers=h(token),
        json={"colors": ["navy", "paars", "regenboog"], "styles": ["Minimalistisch"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["colors"] == ["navy", "paars"], "an unknown colour is dropped, not stored"
    assert body["styles"] == ["Minimalistisch"]
    assert "navy" in body["available_colors"]


def test_the_half_of_a_stijl_dna_the_engine_never_reads_is_kept_as_typed(client, kast):
    """Iemands eigen conclusies over z'n eigen vorm, in z'n eigen woorden.

    Hier wordt met opzet niets gecorrigeerd: de app heeft geen lijst met
    halslijnen om iemand mee tegen te spreken, en een stijlwoord dat de
    aanbevelingen niet kennen is geen reden om het niet te mogen opschrijven.
    """
    token, _ = kast
    r = client.put(
        "/api/me/style",
        headers=h(token),
        json={
            "identity": "Modern, klassiek & elegant",
            "color_season": "Warm & diep",
            "aesthetics": ["quiet luxury", "tijdloos"],
            "necklines": ["V-hals", "open kraag"],
            "silhouettes": ["getailleerd", "high-waist"],
            "fabrics": ["linnen", "fijne breisels"],
            "mantra": "Liever één goede jas dan drie matige.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["identity"] == "Modern, klassiek & elegant"
    assert body["color_season"] == "Warm & diep"
    assert body["aesthetics"] == ["quiet luxury", "tijdloos"]
    assert body["necklines"] == ["V-hals", "open kraag"]
    assert body["silhouettes"] == ["getailleerd", "high-waist"]
    assert body["fabrics"] == ["linnen", "fijne breisels"]
    assert "goede jas" in body["mantra"]

    # En het staat er de volgende keer nog steeds.
    again = client.get("/api/me/style", headers=h(token)).json()
    assert again["identity"] == "Modern, klassiek & elegant"

    # Eén veld wijzigen laat de rest met rust.
    client.put("/api/me/style", headers=h(token), json={"mantra": ""})
    after = client.get("/api/me/style", headers=h(token)).json()
    assert after["mantra"] is None
    assert after["necklines"] == ["V-hals", "open kraag"]


def test_style_dna_gives_outfits_in_your_own_palette_a_nudge(client, kast):
    token, wid = kast
    set_manual_weather(client, token, ["Mild", "Bewolkt"])
    client.put("/api/me/style", headers=h(token), json={"colors": ["navy"]})

    navy_top = item(client, token, wid, "Navy trui", "Trui", color="navy")
    navy_bottom = item(client, token, wid, "Navy broek", "Broek", color="navy")
    red_top = item(client, token, wid, "Rode trui", "Trui", color="rood")
    red_bottom = item(client, token, wid, "Rode broek", "Broek", color="rood")

    make_outfit(client, token, wid, "In mijn kleuren", [navy_top["id"], navy_bottom["id"]],
                weather_tags=["Mild"])
    make_outfit(client, token, wid, "Niet mijn kleuren", [red_top["id"], red_bottom["id"]],
                weather_tags=["Mild"])

    r = client.get("/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid})
    saved = [rec for rec in r.json()["recommendations"] if rec["source"] == "saved"]
    assert saved[0]["outfit_name"] == "In mijn kleuren"
    assert "eigen kleuren" in saved[0]["reason"]


# ---------------------------------------------------------------------------
# Occasions (the admin-managed list)
# ---------------------------------------------------------------------------

def test_the_occasion_list_is_seeded_and_only_admins_may_change_it(client, kast):
    token, _ = kast
    r = client.get("/api/occasions", headers=h(token))
    assert r.status_code == 200, r.text
    names = [o["name"] for o in r.json()]
    assert "Werk" in names and "Uit eten" in names

    refused = client.post("/api/occasions", headers=h(token), json={"name": "Zeilen"})
    assert refused.status_code == 403

    admin = login(client, ADMIN_USER, ADMIN_PASS)
    created = client.post("/api/occasions", headers=h(admin), json={"name": "Zeilen"})
    assert created.status_code == 201, created.text
    assert client.delete(f"/api/occasions/{created.json()['id']}", headers=h(admin)).status_code == 204


def test_garments_carry_the_new_tag_columns(client, kast):
    token, wid = kast
    created = item(
        client, token, wid, "Regenjas", "Jas",
        occasion="Werk,Casual", weather="Regen,Koud", style="Klassiek",
    )
    assert created["occasions"] == ["Werk", "Casual"]
    assert created["weather_tags"] == ["Regen", "Koud"]
    assert created["style_tags"] == ["Klassiek"]

    r = client.patch(
        f"/api/items/{created['id']}", headers=h(token), data={"occasion": "Werk"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["occasions"] == ["Werk"]


# ---------------------------------------------------------------------------
# Looks in an export, and what happens when their author leaves
# ---------------------------------------------------------------------------

def test_an_export_carries_the_looks_and_a_restore_rebuilds_them(client, kast):
    import io
    import json
    import zipfile

    token, wid = kast
    top = item(client, token, wid, "Blauwe trui", "Trui", color="navy", occasion="Werk", weather="Koud")
    bottom = item(client, token, wid, "Nette broek", "Broek", color="beige")
    make_outfit(
        client, token, wid, "Werkdag", [top["id"], bottom["id"]],
        occasions=["Werk"], weather_tags=["Koud", "Bewolkt"], seasons=["Winter"],
    )

    r = client.get(f"/api/backup/wardrobe/{wid}", headers=h(token))
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        payload = json.loads(archive.read("wardrobe.json"))

    looks = payload["wardrobes"][0]["outfits"]
    assert len(looks) == 1
    assert looks[0]["name"] == "Werkdag"
    assert looks[0]["weather"] == ["Koud", "Bewolkt"]
    assert len(looks[0]["items"]) == 2
    # Garments carry their new tags too.
    exported = {i["name"]: i for i in payload["wardrobes"][0]["items"]}
    assert exported["Blauwe trui"]["occasions"] == ["Werk"]
    assert exported["Blauwe trui"]["weather"] == ["Koud"]

    # Put the same archive back into a fresh kast: the look comes back whole.
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, admin, "Ontvanger")
    target_token = login(client, un, pw)
    target, _ = own_wardrobe(client, target_token)

    restored = client.post(
        "/api/backup/restore",
        headers=h(admin),
        files={"file": ("kast.zip", r.content, "application/zip")},
        data={"wardrobe_id": str(target["id"]), "mode": "merge"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["outfits"] == 1

    listed = client.get(
        "/api/outfits", headers=h(target_token), params={"wardrobe_id": target["id"]}
    ).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Werkdag"
    assert listed[0]["weather_tags"] == ["Koud", "Bewolkt"]
    assert len(listed[0]["items"]) == 2


def test_deleting_the_person_who_saved_a_look_keeps_the_look(client):
    """Their authorship moves to the admin, exactly like a garment's does."""
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, ou, op = make_user(client, admin, "Eigenaar")
    guest, gu, gp = make_user(client, admin, "Gast")
    owner_token, guest_token = login(client, ou, op), login(client, gu, gp)
    kast, _ = own_wardrobe(client, owner_token)
    client.post(
        f"/api/wardrobes/{kast['id']}/members",
        headers=h(owner_token),
        json={"username": gu, "role": "editor"},
    )

    top = item(client, owner_token, kast["id"], "Trui", "Trui")
    outfit = make_outfit(client, guest_token, kast["id"], "Van de gast", [top["id"]])

    r = client.delete(f"/api/users/{guest['id']}", headers=h(admin))
    assert r.status_code == 204, r.text

    still_there = client.get(f"/api/outfits/{outfit['id']}", headers=h(owner_token))
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "Van de gast"


def test_the_opruim_list_flags_an_unworn_garment_once_a_wear_log_exists(client, kast):
    """A garment sitting in a look nobody wears is the case this list is for."""
    from datetime import datetime, timedelta, timezone

    from app.routers.insights import _neglected

    token, wid = kast
    old = item(client, token, wid, "Ligt te wachten", "Trui")
    make_outfit(client, token, wid, "Nooit gedragen", [old["id"]])

    # The API cannot add a garment in the past, so the rule is exercised
    # directly on rows shaped the way an old kast's rows are.
    class _Item:
        def __init__(self, item_id, created_at):
            self.id = item_id
            self.created_at = created_at

    class _Outfit:
        def __init__(self, outfit_id, items):
            self.id = outfit_id
            self.items = items

    long_ago = datetime.now(timezone.utc) - timedelta(days=400)
    garment = _Item(1, long_ago)
    outfit = _Outfit(10, [garment])

    # With a wear log that has entries for *other* looks: never worn counts.
    flagged = _neglected([garment], [outfit], {99: ["2026-01-01"]}, 180, True)
    assert [i.id for i in flagged] == [1]

    # Without a wear log, being in a look is reason enough to leave it alone.
    assert _neglected([garment], [outfit], {}, 180, False) == []

    # And a garment in no look at all shows up either way.
    loose = _Item(2, long_ago)
    assert [i.id for i in _neglected([loose], [], {}, 180, False)] == [2]


# ---------------------------------------------------------------------------
# Ontdekken: één zin in plaats van drie keuzelijsten
# ---------------------------------------------------------------------------

def test_a_typed_sentence_becomes_filters(client, kast):
    token, wid = kast
    r = client.get(
        "/api/outfits/discover/describe",
        headers=h(token),
        params={"wardrobe_id": wid, "q": "Bruiloft in juli, hopelijk zonnig"},
    )
    assert r.status_code == 200, r.text
    reading = r.json()["reading"]
    assert reading["occasion"] == "Feest"
    assert reading["season"] == "Zomer"
    assert reading["weather"] == ["Zonnig"]
    assert reading["understood"] is True
    # En het zegt waaróm, zodat een lege lijst geen raadsel is.
    assert "bruiloft" in reading["matched"]


def test_a_sentence_it_cannot_place_says_so(client, kast):
    token, wid = kast
    r = client.get(
        "/api/outfits/discover/describe",
        headers=h(token),
        params={"wardrobe_id": wid, "q": "hmm"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["reading"]["understood"] is False


def test_the_description_separates_what_you_have_from_what_it_invents(client, kast):
    token, wid = kast
    top = add_item(client, token, wid, "Wit overhemd", "Overhemd", color="wit").json()
    bottom = add_item(client, token, wid, "Nette broek", "Broek", color="navy").json()
    saved = client.post(
        f"/api/outfits?wardrobe_id={wid}",
        headers=h(token),
        json={
            "name": "Naar kantoor",
            "item_ids": [top["id"], bottom["id"]],
            "occasions": ["Werk"],
        },
    )
    assert saved.status_code == 201, saved.text

    r = client.get(
        "/api/outfits/discover/describe",
        headers=h(token),
        params={"wardrobe_id": wid, "q": "morgen naar kantoor"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [o["name"] for o in body["saved"]] == ["Naar kantoor"]
    # En wat je al bewaard hebt komt er niet ook nog eens als "voorstel" bij.
    ids = {top["id"], bottom["id"]}
    assert all({i["id"] for i in s["items"]} != ids for s in body["suggestions"])


def test_building_around_one_garment_only_returns_outfits_with_it(client, kast):
    token, wid = kast
    shirt = add_item(client, token, wid, "Wit overhemd", "Overhemd", color="wit").json()
    add_item(client, token, wid, "Grijze trui", "Trui", color="grijs")
    add_item(client, token, wid, "Nette broek", "Broek", color="navy")
    add_item(client, token, wid, "Blauwe jeans", "Jeans", color="denim")

    r = client.get(
        "/api/outfits/discover",
        headers=h(token),
        params={"wardrobe_id": wid, "around": shirt["id"]},
    )
    assert r.status_code == 200, r.text
    results = r.json()
    assert results, "er valt wel iets om dit overhemd heen te bouwen"
    for suggestion in results:
        assert any(i["id"] == shirt["id"] for i in suggestion["items"])


def test_building_around_a_garment_from_another_kast_returns_nothing(client, kast):
    token, wid = kast
    add_item(client, token, wid, "Wit overhemd", "Overhemd", color="wit")
    add_item(client, token, wid, "Nette broek", "Broek", color="navy")

    r = client.get(
        "/api/outfits/discover",
        headers=h(token),
        params={"wardrobe_id": wid, "around": 999_999},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
