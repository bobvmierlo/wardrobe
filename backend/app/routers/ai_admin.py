"""De AI-instellingen, te bedienen door een beheerder in de app.

Bestaat zodat je geen compose-bestand hoeft aan te raken om dit aan te zetten.
Twee dingen zijn hier belangrijker dan het gemak:

* **De sleutel gaat nooit terug over de lijn.** Je kunt 'm zetten en
  vervangen, maar niet uitlezen — het scherm krijgt alleen te horen dát er een
  staat, en de laatste vier tekens zodat je ziet wélke.
* **Wat de operator in de omgeving zette, wint.** Staat er een
  ``WARDROBE_AI_*`` in de omgeving of de ``.env``, dan is dat veld hier
  zichtbaar maar niet te wijzigen. Wat in je compose-bestand staat, staat daar
  met een reden, en een knop in een scherm hoort dat niet stilletjes te
  overrulen.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import app_settings, audit
from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import AiSettingsIn, AiSettingsOut

router = APIRouter(prefix="/api/ai", tags=["ai"])

#: De modellen die het scherm aanbiedt. Vrij tekstveld eronder zou hier alleen
#: maar typefouten opleveren die pas bij de eerste aanroep opvallen.
MODELS: tuple[tuple[str, str], ...] = (
    ("claude-opus-5", "Claude Opus 5 — het slimst, en het duurst"),
    ("claude-sonnet-5", "Claude Sonnet 5 — ruim voldoende voor dit werk"),
    ("claude-haiku-4-5", "Claude Haiku 4.5 — het goedkoopst en het snelst"),
)


def _hint(key: str) -> str | None:
    """De laatste vier tekens, zodat je ziet wélke sleutel er staat."""
    key = (key or "").strip()
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) > 4 else "…"


def _current(db: Session) -> AiSettingsOut:
    config = app_settings.ai_config(db)
    return AiSettingsOut(
        enabled=config.enabled,
        model=config.model,
        effort=config.effort,
        key_set=bool(config.api_key.strip()),
        key_hint=_hint(config.api_key),
        locked=sorted(config.locked),
        models=[{"value": value, "label": label} for value, label in MODELS],
        efforts=list(app_settings.AI_EFFORTS),
        timeout_seconds=settings.ai_timeout_seconds,
    )


@router.get("/settings", response_model=AiSettingsOut)
def read_settings(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Wat er nu staat. Nooit de sleutel zelf."""
    return _current(db)


@router.put("/settings", response_model=AiSettingsOut)
def write_settings(
    body: AiSettingsIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Zet de AI-laag aan of uit, kies een model, of vervang de sleutel.

    Een veld dat de operator in de omgeving heeft vastgezet wordt geweigerd in
    plaats van genegeerd: stilzwijgend niets doen met een knop die wél
    ingedrukt kan worden is de vervelendste soort verrassing.
    """
    config = app_settings.ai_config(db)
    changed: list[str] = []

    def _guard(field: str, label: str) -> None:
        if field in config.locked:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{label} staat vast in de omgeving van de server"
                    f" ({field.upper().replace('AI_', 'WARDROBE_AI_')})."
                    " Pas dat daar aan, of haal het daar weg om het hier te"
                    " kunnen regelen."
                ),
            )

    if body.enabled is not None and body.enabled != config.enabled:
        _guard("ai_enabled", "Aan/uit")
        app_settings.set_bool(db, app_settings.AI_ENABLED, body.enabled, commit=False)
        changed.append("aan" if body.enabled else "uit")

    if body.model is not None and body.model != config.model:
        _guard("ai_model", "Het model")
        if body.model not in {value for value, _label in MODELS}:
            raise HTTPException(status_code=400, detail="Onbekend model")
        app_settings.set_text(db, app_settings.AI_MODEL, body.model, commit=False)
        changed.append(f"model {body.model}")

    if body.effort is not None and body.effort != config.effort:
        _guard("ai_effort", "De effort")
        if body.effort not in app_settings.AI_EFFORTS:
            raise HTTPException(status_code=400, detail="Onbekende effort")
        app_settings.set_text(db, app_settings.AI_EFFORT, body.effort, commit=False)
        changed.append(f"effort {body.effort}")

    if body.api_key is not None:
        _guard("ai_api_key", "De sleutel")
        key = body.api_key.strip()
        # Leeg betekent wissen — dat is hoe je de laag uit krijgt zonder de
        # schakelaar om te zetten, en het is niet per ongeluk te doen omdat het
        # veld leeg laten simpelweg niets meestuurt.
        app_settings.set_text(db, app_settings.AI_API_KEY, key, commit=False)
        changed.append("sleutel vervangen" if key else "sleutel gewist")

    db.commit()
    if changed:
        audit.record(
            db,
            "ai.settings",
            "AI-instellingen gewijzigd: " + ", ".join(changed),
            user=admin,
        )
    return _current(db)
