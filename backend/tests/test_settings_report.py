"""The startup report: every setting, its value, and where it came from.

Asserted against the app's own ring buffer rather than stdout, because that
buffer is what an admin reads under Instellingen → Logboek. If a line is wrong
here, it is wrong on the screen someone is actually looking at.
"""

import pytest

from app import settings_report
from app.config import Settings, settings
from app.logging_setup import buffer_handler


def lines() -> list[str]:
    """Run the report and return what it wrote, oldest first."""
    buffer_handler.clear()
    settings_report.report()
    return [r["message"] for r in reversed(buffer_handler.snapshot(limit=500))]


def line_for(variable: str) -> str:
    matches = [ln for ln in lines() if variable in ln]
    assert matches, f"{variable} was not reported at all"
    # The header mentions no variable, so a single match is the row itself.
    assert len(matches) == 1, f"{variable} reported {len(matches)} times: {matches}"
    return matches[0]


def test_every_setting_is_reported_exactly_once():
    reported = lines()
    for field in Settings.model_fields:
        variable = f"WARDROBE_{field.upper()}"
        hits = [ln for ln in reported if variable in ln]
        assert len(hits) == 1, f"{variable}: {len(hits)} lines"


def test_a_value_you_set_yourself_says_so_and_is_starred(monkeypatch):
    monkeypatch.setenv("WARDROBE_MIN_PASSWORD_LENGTH", "12")
    monkeypatch.setattr(settings, "min_password_length", 12)
    row = line_for("WARDROBE_MIN_PASSWORD_LENGTH")
    assert "= 12" in row
    assert "[omgeving]" in row
    assert row.lstrip().startswith("*"), row  # differs from the built-in default


def test_an_untouched_value_says_standaard():
    row = line_for("WARDROBE_COOKIE_SECURE")
    assert "= auto" in row
    assert "[standaard]" in row
    assert not row.lstrip().startswith("*")


def test_setting_a_value_that_equals_the_default_is_not_starred(monkeypatch):
    """Honest rather than flattering: you set it, but you changed nothing."""
    monkeypatch.setenv("WARDROBE_LOG_LEVEL", settings.log_level)
    row = line_for("WARDROBE_LOG_LEVEL")
    assert "[omgeving]" in row
    assert not row.lstrip().startswith("*")


def test_a_dotenv_file_is_named_as_the_source(monkeypatch, tmp_path):
    """Running the backend directly, settings come from a .env next to it."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "WARDROBE_OIDC_BUTTON_LABEL=Inloggen met Authentik\n"
        "export WARDROBE_OIDC_ADMIN_GROUP=kast-admins\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(settings.model_config, "env_file", str(env_file))
    monkeypatch.delenv("WARDROBE_OIDC_BUTTON_LABEL", raising=False)
    monkeypatch.delenv("WARDROBE_OIDC_ADMIN_GROUP", raising=False)

    assert "[.env-bestand]" in line_for("WARDROBE_OIDC_BUTTON_LABEL")
    # Also picked up through an "export" prefix, which people do write.
    assert "[.env-bestand]" in line_for("WARDROBE_OIDC_ADMIN_GROUP")


def test_the_environment_wins_over_a_dotenv_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("WARDROBE_OIDC_BUTTON_LABEL=uit het bestand\n", encoding="utf-8")
    monkeypatch.setitem(settings.model_config, "env_file", str(env_file))
    monkeypatch.setenv("WARDROBE_OIDC_BUTTON_LABEL", "uit de omgeving")
    assert "[omgeving]" in line_for("WARDROBE_OIDC_BUTTON_LABEL")


def test_a_missing_dotenv_file_is_not_a_problem(monkeypatch, tmp_path):
    monkeypatch.setitem(settings.model_config, "env_file", str(tmp_path / "nope.env"))
    assert "[standaard]" in line_for("WARDROBE_COOKIE_SECURE")


@pytest.mark.parametrize(
    "field, variable",
    [
        ("secret_key", "WARDROBE_SECRET_KEY"),
        ("admin_password", "WARDROBE_ADMIN_PASSWORD"),
        ("oidc_client_secret", "WARDROBE_OIDC_CLIENT_SECRET"),
    ],
)
def test_a_secret_is_never_printed(monkeypatch, field, variable):
    """The log is readable inside the app, so it must not carry the keys."""
    value = "geheim-" + field + "-abcdefghijklmnop"
    monkeypatch.setattr(settings, field, value)
    reported = lines()
    assert not any(value in ln for ln in reported), f"{field} leaked into the log"
    row = next(ln for ln in reported if variable in ln)
    # Present and how long, which is what answers "did it arrive?".
    assert f"ingesteld, {len(value)} tekens" in row


def test_an_empty_secret_is_reported_as_not_set(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_secret", "")
    assert "(niet ingesteld)" in line_for("WARDROBE_OIDC_CLIENT_SECRET")


def test_an_empty_ordinary_value_is_marked_empty_rather_than_blank(monkeypatch):
    monkeypatch.setattr(settings, "oidc_allowed_groups", "")
    assert "(leeg)" in line_for("WARDROBE_OIDC_ALLOWED_GROUPS")


def test_a_very_long_value_is_shortened(monkeypatch):
    """The CSP would otherwise wrap past the edge of a terminal."""
    row = line_for("WARDROBE_CONTENT_SECURITY_POLICY")
    assert "…" in row
    assert len(row) < 140


def test_booleans_read_as_true_and_false(monkeypatch):
    monkeypatch.setattr(settings, "oidc_auto_create", True)
    assert "= true" in line_for("WARDROBE_OIDC_AUTO_CREATE")
    monkeypatch.setattr(settings, "oidc_auto_create", False)
    assert "= false" in line_for("WARDROBE_OIDC_AUTO_CREATE")


def test_the_header_explains_the_three_sources():
    header = lines()[0]
    assert "Actieve instellingen" in header
    for word in ("omgeving", ".env-bestand", "standaard"):
        assert word in header


def test_the_paths_that_hold_the_data_are_logged():
    reported = lines()
    assert any(str(settings.db_path) in ln for ln in reported)
    assert any(str(settings.uploads_dir) in ln for ln in reported)


def test_the_groups_are_there_to_skim_by():
    reported = lines()
    for heading in ("Opslag en basis", "Beveiliging", "Inloggen via SSO"):
        assert any(heading in ln for ln in reported), heading
