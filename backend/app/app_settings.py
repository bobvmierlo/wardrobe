"""Settings a beheerder can change from inside the app.

:mod:`app.config` holds what the *operator* sets before the container starts
(paths, secrets, log level). This module holds what the *beheerder* changes
while it runs, stored in the ``app_settings`` table so a flip survives a
restart without anyone touching a compose file.

Values are plain strings on disk; every setting gets a typed accessor here so
the callers never parse anything themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting
from .settings_report import provided

#: Whether anyone may create their own account from the login screen. Off by
#: default: the app is invitation-only until a beheerder says otherwise.
SELF_REGISTRATION = "self_registration"

#: De optionele AI-laag. Deze vier staan hier zodat een beheerder ze in de app
#: kan zetten in plaats van in een compose-bestand — zie :func:`ai_config` voor
#: wat er gebeurt als de operator ze tóch in de omgeving heeft gezet.
AI_ENABLED = "ai_enabled"
AI_API_KEY = "ai_api_key"
AI_MODEL = "ai_model"
AI_EFFORT = "ai_effort"

_TRUE = {"1", "true", "yes", "on"}


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    return row.value.strip().lower() in _TRUE


def set_bool(db: Session, key: str, value: bool, *, commit: bool = True) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value="true" if value else "false"))
    else:
        row.value = "true" if value else "false"
    if commit:
        db.commit()


def self_registration_open(db: Session) -> bool:
    """True when the login screen may offer "account aanmaken"."""
    return get_bool(db, SELF_REGISTRATION, default=False)


def get_text(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return row.value if row is not None else default


def set_text(db: Session, key: str, value: str, *, commit: bool = True) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    if commit:
        db.commit()


@dataclass(frozen=True)
class AiConfig:
    """Wat de AI-laag mag en waarmee, op dit moment.

    Samengesteld per verzoek in plaats van bij het opstarten, omdat een
    beheerder het in de app kan wijzigen en dat meteen moet gelden.
    """
    enabled: bool
    api_key: str
    model: str
    effort: str
    timeout_seconds: float
    refusal_fallback: bool
    #: Welke velden de operator in de omgeving heeft vastgezet. Die zijn in de
    #: app zichtbaar maar niet te wijzigen — wat in je compose-bestand staat,
    #: staat daar met een reden.
    locked: frozenset[str] = frozenset()

    @property
    def usable(self) -> bool:
        """Aan én een sleutel. Zonder allebei bestaat de laag niet."""
        return bool(self.enabled and self.api_key.strip())


#: Welke effort-standen de app aanbiedt. De API kent er meer, maar dit is
#: invulwerk: hoger dan "medium" kost geld zonder dat het iets oplevert.
AI_EFFORTS = ("low", "medium", "high")


def ai_config(db: Session) -> AiConfig:
    """De AI-instellingen, met de omgeving boven de database.

    Heeft de operator ``WARDROBE_AI_*`` meegegeven, dan wint dat en staat het
    veld op slot in de app. Zo blijft een installatie die alles via een
    compose-bestand regelt precies doen wat daar staat, terwijl een beheerder
    die dat niet doet het gewoon in de app kan instellen.
    """
    locked = {
        field
        for field in ("ai_enabled", "ai_api_key", "ai_model", "ai_effort")
        if provided(field)
    }

    def _pick(field: str, key: str, fallback):
        if field in locked:
            return getattr(settings, field)
        stored = get_text(db, key, "")
        if stored == "":
            return getattr(settings, field)
        return fallback(stored)

    return AiConfig(
        enabled=_pick(
            "ai_enabled", AI_ENABLED, lambda v: v.strip().lower() in _TRUE
        ),
        api_key=_pick("ai_api_key", AI_API_KEY, lambda v: v),
        model=_pick("ai_model", AI_MODEL, lambda v: v),
        effort=_pick("ai_effort", AI_EFFORT, lambda v: v),
        # Deze twee blijven bewust alleen in de omgeving: een time-out en een
        # terugvalmodel zijn iets voor wie de server beheert, niet iets om in
        # een scherm aan te bieden.
        timeout_seconds=settings.ai_timeout_seconds,
        refusal_fallback=settings.ai_refusal_fallback,
        locked=frozenset(locked),
    )
