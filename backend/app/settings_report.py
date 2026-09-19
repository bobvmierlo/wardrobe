"""Writing every effective setting to the log at startup.

"Is this thing actually reading my .env?" is the first question of every
self-hosted debugging session, and until now the only way to answer it was to
change a value and see whether the app behaved differently. So the app says it
out loud instead: one line per setting, the value it is really using, and where
that value came from.

Three sources, and they are genuinely distinguishable:

``omgeving``
    The variable is present in the process environment. Under Docker that means
    it came out of your ``.env`` (or the host environment) via the
    ``environment:`` list in ``docker-compose.yml``.
``.env-bestand``
    Not in the environment, but named in a ``.env`` next to the app — how the
    backend picks up settings when you run it directly, without Docker.
``standaard``
    Nowhere to be found, so the built-in value from :mod:`app.config` applies.

That distinction only survives if nothing sets the variable on the app's behalf.
``WARDROBE_X: "${WARDROBE_X:-iets}"`` in a compose file does exactly that: the
variable is always set, to the fallback when ``.env`` is silent, and the
container has no way to tell the two apart. Which is why the compose file passes
these through by bare name instead, letting an absent variable stay absent and
:mod:`app.config` own every default. Keep it that way and this report stays
honest.

Secrets are never printed. A secret is reported as set-or-not and how long it
is, which is enough to tell "the variable arrived" from "the variable is empty"
without putting the key in a log an admin can read back in the app.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import Settings, settings
from .logging_setup import get_logger

log = get_logger("config")

#: Never printed. Their presence and length are, because "did my secret arrive?"
#: is a fair question and "what is it?" is not.
SECRET_FIELDS = frozenset({"secret_key", "admin_password", "oidc_client_secret"})

#: Headings, so thirty lines of output can be skimmed instead of read. Each
#: entry is (first field of the group, heading).
GROUPS: tuple[tuple[str, str], ...] = (
    ("data_dir", "Opslag en basis"),
    ("login_max_attempts", "Beveiliging"),
    ("weather_enabled", "Weer"),
    ("oidc_enabled", "Inloggen via SSO (OpenID Connect)"),
    ("frontend_dir", "Intern"),
)


def _env_name(field: str) -> str:
    return f"WARDROBE_{field.upper()}"


def _environ_names() -> set[str]:
    """Every WARDROBE_* name in the environment, upper-cased.

    Upper-cased because pydantic-settings matches case-insensitively, so
    ``wardrobe_log_level`` configures the app just as well and should be
    reported as having done so.
    """
    return {k.upper() for k in os.environ if k.upper().startswith("WARDROBE_")}


def _dotenv_names() -> set[str]:
    """Names assigned in the ``.env`` the app itself reads, if there is one.

    Parsed rather than inferred: a value in ``.env`` that happens to equal the
    built-in default would otherwise be reported as "standaard", which is the
    one answer that would send someone looking in the wrong place.
    """
    configured = settings.model_config.get("env_file")
    if not configured:
        return set()
    path = Path(configured)
    if not path.is_file():
        return set()
    names: set[str] = set()
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name = line.split("=", 1)[0].strip()
            if name.startswith("export "):
                name = name[len("export "):].strip()
            if name:
                names.add(name.upper())
    except OSError as exc:
        log.warning("Kon %s niet lezen om de herkomst te bepalen: %s", path, exc)
        return set()
    return names


def _shown(field: str, value: object) -> str:
    """How a value appears in the log."""
    if field in SECRET_FIELDS:
        text = "" if value is None else str(value)
        if not text:
            return "(niet ingesteld)"
        return f"(ingesteld, {len(text)} tekens)"
    if value is None:
        return "(niet ingesteld)"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text == "":
        return "(leeg)"
    # A long policy string would push the alignment off a terminal; the full
    # value is in the header the app actually sends.
    if len(text) > 70:
        return text[:67] + "…"
    return text


def report() -> None:
    """Log every setting, its effective value and where it came from."""
    from_environ = _environ_names()
    from_dotenv = _dotenv_names()
    fields = list(Settings.model_fields)
    headings = dict(GROUPS)

    rows: list[tuple[str, str, str, str, bool]] = []
    for field in fields:
        name = _env_name(field)
        value = getattr(settings, field)
        default = Settings.model_fields[field].default
        if name in from_environ:
            source = "omgeving"
        elif name in from_dotenv:
            source = ".env-bestand"
        else:
            source = "standaard"
        changed = source != "standaard" and value != default
        rows.append((field, name, _shown(field, value), source, changed))

    width = max(len(name) for _field, name, _v, _s, _c in rows)
    changed_count = sum(1 for *_rest, changed in rows if changed)
    log.info(
        "Actieve instellingen (%d; %d afwijkend van de standaard). Herkomst:"
        " 'omgeving' = uit je .env of docker-compose, '.env-bestand' = uit een"
        " .env naast de app, 'standaard' = de ingebouwde waarde.",
        len(rows),
        changed_count,
    )
    for field, name, shown, source, changed in rows:
        heading = headings.get(field)
        if heading:
            log.info("  -- %s --", heading)
        log.info(
            "  %s %-*s = %s  [%s]",
            "*" if changed else " ",
            width,
            name,
            shown,
            source,
        )

    # Two derived paths that are not settings but are the first thing anyone
    # checks when data appears to have vanished.
    log.info("  (database: %s)", settings.db_path)
    log.info("  (foto's:   %s)", settings.uploads_dir)
