"""De AI-instellingen zoals een beheerder ze in de app bedient.

Twee dingen staan hier centraal: de sleutel mag er nooit uit komen, en wat de
operator in de omgeving heeft gezet mag een knop in een scherm niet stilletjes
overrulen.
"""

import pytest

from app import app_settings
from app.config import settings
from tests.test_wardrobes import ADMIN_PASS, ADMIN_USER, h, login, make_user


@pytest.fixture
def admin(client):
    token = login(client, ADMIN_USER, ADMIN_PASS)
    yield token
    client.put(
        "/api/ai/settings", headers=h(token), json={"enabled": False, "api_key": ""}
    )


def read(client, token):
    r = client.get("/api/ai/settings", headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# De sleutel
# ---------------------------------------------------------------------------

def test_the_key_never_comes_back_out(client, admin):
    r = client.put(
        "/api/ai/settings",
        headers=h(admin),
        json={"enabled": True, "api_key": "sk-ant-geheim-abcd1234"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["key_set"] is True
    assert body["key_hint"] == "…1234", "alleen genoeg om te zien wélke sleutel"
    assert "sk-ant-geheim" not in r.text, "de sleutel zelf verlaat de server niet"
    assert "api_key" not in body

    # Ook niet bij een gewone uitlezing.
    again = client.get("/api/ai/settings", headers=h(admin))
    assert "sk-ant-geheim" not in again.text


def test_an_empty_key_clears_it_and_leaving_it_out_keeps_it(client, admin):
    client.put(
        "/api/ai/settings",
        headers=h(admin),
        json={"enabled": True, "api_key": "sk-ant-blijft-staan"},
    )
    # Alleen het model wijzigen laat de sleutel met rust.
    r = client.put("/api/ai/settings", headers=h(admin), json={"model": "claude-sonnet-5"})
    assert r.status_code == 200, r.text
    assert r.json()["key_set"] is True
    assert r.json()["model"] == "claude-sonnet-5"

    # Een lege string is wél een opdracht.
    r = client.put("/api/ai/settings", headers=h(admin), json={"api_key": ""})
    assert r.status_code == 200, r.text
    assert r.json()["key_set"] is False
    assert r.json()["key_hint"] is None


def test_the_layer_is_only_usable_with_both_switch_and_key(client, admin):
    def usable():
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            return app_settings.ai_config(db).usable
        finally:
            db.close()

    client.put("/api/ai/settings", headers=h(admin), json={"enabled": True, "api_key": ""})
    assert usable() is False

    client.put("/api/ai/settings", headers=h(admin), json={"api_key": "sk-ant-test"})
    assert usable() is True

    client.put("/api/ai/settings", headers=h(admin), json={"enabled": False})
    assert usable() is False


# ---------------------------------------------------------------------------
# Wie mag hier aan zitten
# ---------------------------------------------------------------------------

def test_only_an_admin_may_see_or_change_this(client):
    beheerder = login(client, ADMIN_USER, ADMIN_PASS)
    _, un, pw = make_user(client, beheerder, "Gewone gebruiker")
    gewoon = login(client, un, pw)

    assert client.get("/api/ai/settings", headers=h(gewoon)).status_code == 403
    assert client.put(
        "/api/ai/settings", headers=h(gewoon), json={"enabled": True}
    ).status_code == 403


# ---------------------------------------------------------------------------
# De omgeving wint
# ---------------------------------------------------------------------------

def test_what_the_operator_pinned_is_locked_not_silently_ignored(client, admin, monkeypatch):
    """Een knop die wél indrukbaar is maar niets doet, is de nare variant."""
    monkeypatch.setattr(
        app_settings, "provided", lambda field: field in {"ai_enabled", "ai_api_key"}
    )
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "sk-ant-uit-de-omgeving")

    body = read(client, admin)
    assert body["enabled"] is True, "de omgeving bepaalt wat er draait"
    assert body["key_set"] is True
    assert sorted(body["locked"]) == ["ai_api_key", "ai_enabled"]

    r = client.put("/api/ai/settings", headers=h(admin), json={"enabled": False})
    assert r.status_code == 409
    assert "omgeving" in r.json()["detail"]

    r = client.put("/api/ai/settings", headers=h(admin), json={"api_key": "sk-ant-anders"})
    assert r.status_code == 409

    # Wat níét vastligt blijft gewoon te wijzigen.
    r = client.put("/api/ai/settings", headers=h(admin), json={"model": "claude-haiku-4-5"})
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "claude-haiku-4-5"


def test_setting_a_pinned_field_to_the_same_value_is_not_a_conflict(client, admin, monkeypatch):
    """Het scherm stuurt alles mee; alleen een échte wijziging mag botsen."""
    monkeypatch.setattr(app_settings, "provided", lambda field: field == "ai_enabled")
    monkeypatch.setattr(settings, "ai_enabled", True)

    r = client.put("/api/ai/settings", headers=h(admin), json={"enabled": True})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Modellen en effort
# ---------------------------------------------------------------------------

def test_the_screen_gets_the_choices_it_should_offer(client, admin):
    body = read(client, admin)
    values = [m["value"] for m in body["models"]]
    assert "claude-opus-5" in values
    assert all("label" in m and m["label"] for m in body["models"])
    assert body["efforts"] == list(app_settings.AI_EFFORTS)


def test_a_model_or_effort_the_app_does_not_offer_is_refused(client, admin):
    r = client.put("/api/ai/settings", headers=h(admin), json={"model": "gpt-verzonnen"})
    assert r.status_code == 400
    assert "model" in r.json()["detail"].lower()

    r = client.put("/api/ai/settings", headers=h(admin), json={"effort": "extreem"})
    assert r.status_code == 400


def test_a_change_lands_in_the_audit_trail(client, admin):
    client.put(
        "/api/ai/settings",
        headers=h(admin),
        json={"enabled": True, "api_key": "sk-ant-test", "model": "claude-sonnet-5"},
    )
    entries = client.get(
        "/api/audit", headers=h(admin), params={"action": "ai.settings"}
    ).json()["entries"]
    assert entries, "een beheerder hoort terug te kunnen zien dat dit is gewijzigd"
    detail = entries[0]["detail"]
    assert "sleutel vervangen" in detail
    assert "sk-ant-test" not in detail, "en de sleutel staat er niet in"
