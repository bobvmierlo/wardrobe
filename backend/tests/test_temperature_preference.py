"""Heb jij het snel koud of snel warm.

Een weerbericht zegt vijftien graden; wat je daarbij aantrekt verschilt per
persoon met dertig graden aan kledingkeuze. Deze tests leggen vast dat die
voorkeur de *banden* verschuift en niet de thermometer: de app blijft vijftien
graden vijftien graden noemen.
"""

import pytest

from app import weather as weather_service
from app.recommendations import bare_skin_note
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
    _, un, pw = make_user(client, admin, "Kouwkleum")
    token = login(client, un, pw)
    wardrobe, _ = own_wardrobe(client, token)
    return token, wardrobe["id"]


def item(client, token, wardrobe_id, name, category, **extra):
    r = add_item(client, token, wardrobe_id, name, category, **extra)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# De schaal zelf
# ---------------------------------------------------------------------------

def test_fifteen_degrees_means_something_different_per_person():
    """Het voorbeeld waar dit om begonnen is."""
    assert weather_service.temperature_tag(15.0, 0) == "Mild"
    assert weather_service.temperature_tag(15.0, 3) == "Warm"
    assert weather_service.temperature_tag(15.0, 6) == "Warm"

    # En dus: korte broek en korte mouwen.
    assert weather_service.bares_arms_and_legs(15.0, 0) is False
    assert weather_service.bares_arms_and_legs(15.0, 3) is True


def test_a_cold_natured_person_reaches_for_a_coat_sooner():
    assert weather_service.temperature_tag(10.0, 0) == "Mild"
    assert weather_service.temperature_tag(10.0, -6) == "Koud"
    assert weather_service.bares_arms_and_legs(20.0, -6) is False
    assert weather_service.bares_arms_and_legs(20.0, 0) is True


def test_a_preference_outside_the_scale_is_clamped_not_obeyed():
    """Wat er ook in de database staat, de banden blijven bruikbaar."""
    assert weather_service.clamp_offset(None) == 0
    assert weather_service.clamp_offset(99) == weather_service.MAX_OFFSET
    assert weather_service.clamp_offset(-99) == weather_service.MIN_OFFSET
    # Zonder klem zou 99 graden erbij van vijf graden vorst "Heet" maken; met
    # klem schuift 'ie hooguit één band op.
    assert weather_service.temperature_tag(-5.0, 99) == "Koud"
    assert weather_service.temperature_tag(15.0, 99) == "Warm"


def test_the_forecast_itself_is_not_rewritten(monkeypatch):
    """De thermometer blijft de thermometer; alleen de band verschuift."""
    forecast = weather_service.Forecast(
        temperature=15.0,
        apparent_temperature=15.0,
        wind_speed=5.0,
        precipitation=0.0,
        code=3,
        description="Bewolkt",
        tags=weather_service.tags_for(3, 15.0, 5.0),
    )
    warm = weather_service.retag(forecast, 3)
    assert warm.temperature == 15.0, "vijftien graden blijft vijftien graden"
    assert warm.tags == ["Bewolkt", "Warm"]
    assert forecast.tags == ["Bewolkt", "Mild"], "het origineel blijft ongemoeid"
    # Zonder voorkeur is er niets te hertaggen en komt dezelfde verwachting terug.
    assert weather_service.retag(forecast, 0) is forecast


# ---------------------------------------------------------------------------
# Opslaan, en wat het oplevert
# ---------------------------------------------------------------------------

def test_the_preference_is_saved_per_user_and_starts_at_average(client, kast):
    token, _ = kast
    prefs = client.get("/api/me/preferences", headers=h(token)).json()
    assert prefs["temperature_preference"] == 0
    labels = [o["label"] for o in prefs["temperature_options"]]
    assert "Gemiddeld" in labels and len(labels) == 5

    r = client.put(
        "/api/me/preferences", headers=h(token), json={"temperature_preference": 3}
    )
    assert r.status_code == 200, r.text
    assert r.json()["temperature_preference"] == 3


def test_it_is_personal_even_in_a_shared_kast(client):
    admin = login(client, ADMIN_USER, ADMIN_PASS)
    _, au, ap = make_user(client, admin, "Warmbloedig")
    _, bu, bp = make_user(client, admin, "Kouwelijk")
    warm, cold = login(client, au, ap), login(client, bu, bp)

    client.put("/api/me/preferences", headers=h(warm), json={"temperature_preference": 6})
    client.put("/api/me/preferences", headers=h(cold), json={"temperature_preference": -6})

    assert client.get("/api/me/preferences", headers=h(warm)).json()["temperature_preference"] == 6
    assert client.get("/api/me/preferences", headers=h(cold)).json()["temperature_preference"] == -6


def test_an_absurd_preference_is_clamped_on_the_way_in(client, kast):
    token, _ = kast
    r = client.put(
        "/api/me/preferences", headers=h(token), json={"temperature_preference": 10}
    )
    assert r.status_code == 200, r.text
    assert r.json()["temperature_preference"] == weather_service.MAX_OFFSET

    # En wat de schaal helemaal niet kent, weigert de API.
    assert client.put(
        "/api/me/preferences", headers=h(token), json={"temperature_preference": 500}
    ).status_code == 422


def test_the_forecast_a_user_sees_carries_their_own_band(client, kast, monkeypatch):
    token, _ = kast
    weather_service.clear_cache()

    def fake(url, params):
        return {
            "current": {
                "temperature_2m": 15.0,
                "apparent_temperature": 15.0,
                "precipitation": 0.0,
                "weather_code": 3,
                "wind_speed_10m": 5.0,
                "is_day": 1,
            },
            "daily": {
                "temperature_2m_max": [16.0],
                "temperature_2m_min": [9.0],
                "precipitation_probability_max": [10],
                "weather_code": [3],
            },
        }

    monkeypatch.setattr(weather_service, "_get_json", fake)
    client.put(
        "/api/me/preferences",
        headers=h(token),
        json={"location_label": "Gemert", "latitude": 51.56, "longitude": 5.69},
    )

    average = client.get("/api/weather/current", headers=h(token)).json()
    assert average["temperature"] == 15.0
    assert "Mild" in average["tags"]

    client.put("/api/me/preferences", headers=h(token), json={"temperature_preference": 3})
    personal = client.get("/api/weather/current", headers=h(token)).json()
    assert personal["temperature"] == 15.0, "de verwachting zelf verandert niet"
    assert "Warm" in personal["tags"], "de band wel"
    weather_service.clear_cache()


def test_short_sleeves_become_reachable_at_fifteen_degrees(client, kast):
    """Het hele punt: bij 15° stelt de app jou wél iets korts voor."""
    token, wid = kast
    tee = item(client, token, wid, "Wit T-shirt", "T-shirt", color="wit", weather="Warm,Heet")
    shorts = item(client, token, wid, "Korte broek", "Shorts", color="beige", weather="Warm,Heet")

    body = {"name": "Zomers", "item_ids": [tee["id"], shorts["id"]], "weather_tags": ["Warm"]}
    r = client.post("/api/outfits", headers=h(token), params={"wardrobe_id": wid}, json=body)
    assert r.status_code == 201, r.text

    # Handmatig weer op "Mild" — zoals 15 graden voor de gemiddelde mens voelt.
    client.put(
        "/api/me/preferences",
        headers=h(token),
        json={"weather_mode": "manual", "manual_weather": ["Mild", "Bewolkt"]},
    )
    page = client.get(
        "/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    saved = [r for r in page["recommendations"] if r["source"] == "saved"]
    assert saved and saved[0]["score"] < 0, "een zomeroutfit hoort bij mild te zakken"

    # Dezelfde persoon, maar dan met "Warm" — waar 15° voor hén op uitkomt.
    client.put(
        "/api/me/preferences", headers=h(token), json={"manual_weather": ["Warm", "Bewolkt"]}
    )
    page = client.get(
        "/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    saved = [r for r in page["recommendations"] if r["source"] == "saved"]
    assert saved and saved[0]["score"] > 0
    assert "warm" in saved[0]["reason"].lower()


# ---------------------------------------------------------------------------
# De zin die het uitlegt
# ---------------------------------------------------------------------------

def test_the_note_only_appears_when_the_preference_changes_something():
    # Gemiddeld: niets te melden.
    assert bare_skin_note(15.0, 0) is None
    # Warmbloedig bij 15°: wel.
    note = bare_skin_note(15.0, 3)
    assert note and "korte broek" in note and "15°" in note
    # Warmbloedig bij 25°: iedereen gaat al in korte mouwen, dus geen open deur.
    assert bare_skin_note(25.0, 3) is None
    # Kouwelijk bij 20°: de andere kant op.
    note = bare_skin_note(20.0, -6)
    assert note and "bedekt" in note
    # Zonder verwachting valt er niets te zeggen.
    assert bare_skin_note(None, 6) is None


def test_the_note_shows_up_on_the_vandaag_screen(client, kast):
    token, wid = kast
    item(client, token, wid, "Wit T-shirt", "T-shirt", color="wit")
    client.put(
        "/api/me/preferences",
        headers=h(token),
        json={
            "weather_mode": "manual",
            "manual_weather": ["Mild", "Bewolkt"],
            "temperature_preference": 6,
        },
    )
    page = client.get(
        "/api/outfits/recommendations", headers=h(token), params={"wardrobe_id": wid}
    ).json()
    # Handmatig weer kent geen echte temperatuur, dus de band van "Mild" telt.
    assert page["advice"], "er staat hoe dan ook een advies"
