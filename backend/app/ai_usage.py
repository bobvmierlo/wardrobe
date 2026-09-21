"""Bijhouden wat de AI-laag heeft gekost, en dat kunnen optellen.

:mod:`app.ai` praat met Anthropic en telt de tokens; deze module bewaart ze en
maakt er een totaal van. Twee modules omdat het twee dingen zijn: de ene mag
geen database kennen (dan is 'ie te testen zonder), de andere hoeft niets van
HTTP te weten.

Waarom dit er überhaupt is: dit is het enige in de app dat geld kost, en het
kost geld van degene die de sleutel heeft ingevuld. Een schakelaar die per
druk op de knop factureert hoort te kunnen zeggen hoe vaak er is gedrukt — en
wat dat ongeveer was. "Ongeveer", want het bedrag is onze eigen rekensom op de
gepubliceerde tarieven (zie :mod:`app.ai_pricing`), niet de factuur zelf.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .ai import AiCall
from .ai_pricing import cost_millicents
from .logging_setup import get_logger
from .models import AiUsage, User, utcnow

log = get_logger("ai")

#: Hoe een verzoek in het scherm heet. Een onbekende sleutel wordt getoond zoals
#: 'ie is: beter een raar woord dan een lege regel.
PURPOSE_LABELS: dict[str, str] = {
    "tags": "Tags aanvullen",
    "looks": "Looks samenstellen",
    "names": "Looks een naam geven",
}


def record(db: Session, calls: list[AiCall], user: User | None = None) -> None:
    """Schrijf weg wat er is verstuurd. Faalt nooit de knop.

    Het bijhouden van de rekening is bijzaak vergeleken met het werk dat de
    gebruiker vroeg: gaat dit mis, dan komt dat in het log en gaat het
    antwoord gewoon terug. Een teller is geen reden om een geslaagde actie
    alsnog te laten mislukken.
    """
    if not calls:
        return
    try:
        for call in calls:
            db.add(
                AiUsage(
                    purpose=call.purpose or "onbekend",
                    model=call.model,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    cache_read_tokens=call.cache_read_tokens,
                    cache_write_tokens=call.cache_write_tokens,
                    cost_millicents=cost_millicents(
                        call.model,
                        call.input_tokens,
                        call.output_tokens,
                        call.cache_read_tokens,
                        call.cache_write_tokens,
                    ),
                    user_id=user.id if user is not None else None,
                )
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - een teller mag niets omver halen
        db.rollback()
        log.warning("AI-verbruik kon niet worden vastgelegd: %s", exc)


@dataclass
class UsageLine:
    """Eén regel in het overzicht: alles van één soort verzoek, of één model."""

    #: Leeg bij aanmaken en meteen daarna gezet: deze regels ontstaan in een
    #: ``defaultdict`` terwijl de rijen langskomen.
    label: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_millicents: int = 0
    #: True zodra er één verzoek bij zit waarvan we de prijs niet kennen, zodat
    #: het scherm kan zeggen dat het bedrag onvolledig is in plaats van te laag.
    partial: bool = False


@dataclass
class UsageReport:
    """Wat de AI-laag tot nu toe heeft gedaan en ongeveer gekost."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_millicents: int = 0
    partial: bool = False
    first_call: str | None = None
    last_call: str | None = None
    #: Dezelfde sommen over de laatste dertig dagen — "wat heeft het ooit
    #: gekost" en "wat kost het nu" zijn verschillende vragen.
    month_calls: int = 0
    month_cost_millicents: int = 0
    by_purpose: list[UsageLine] = field(default_factory=list)
    by_model: list[UsageLine] = field(default_factory=list)


def _add(line: UsageLine, row: AiUsage) -> None:
    line.calls += 1
    line.input_tokens += row.input_tokens or 0
    line.output_tokens += row.output_tokens or 0
    if row.cost_millicents is None:
        line.partial = True
    else:
        line.cost_millicents += row.cost_millicents


def report(db: Session) -> UsageReport:
    """Alles bij elkaar opgeteld.

    Over de hele tabel in één keer: dit zijn hooguit een paar honderd rijen per
    jaar (één per knopdruk met AI), en dan is optellen in Python eerlijker dan
    vier aggregatiequery's die ieder een andere kant van dezelfde som doen.
    """
    rows = db.query(AiUsage).order_by(AiUsage.created_at).all()
    result = UsageReport()
    if not rows:
        return result

    cutoff = utcnow().replace(tzinfo=None) - timedelta(days=30)
    purposes: dict[str, UsageLine] = defaultdict(UsageLine)
    models: dict[str, UsageLine] = defaultdict(UsageLine)

    for row in rows:
        result.calls += 1
        result.input_tokens += row.input_tokens or 0
        result.output_tokens += row.output_tokens or 0
        if row.cost_millicents is None:
            result.partial = True
        else:
            result.cost_millicents += row.cost_millicents

        if row.created_at is not None and row.created_at >= cutoff:
            result.month_calls += 1
            result.month_cost_millicents += row.cost_millicents or 0

        purpose = purposes[row.purpose]
        purpose.label = PURPOSE_LABELS.get(row.purpose, row.purpose)
        _add(purpose, row)

        model = models[row.model]
        model.label = row.model
        _add(model, row)

    result.first_call = rows[0].created_at.isoformat() if rows[0].created_at else None
    result.last_call = rows[-1].created_at.isoformat() if rows[-1].created_at else None
    result.by_purpose = sorted(purposes.values(), key=lambda l: -l.calls)
    result.by_model = sorted(models.values(), key=lambda l: -l.calls)
    return result


def clear(db: Session) -> int:
    """Gooi de teller leeg. Geeft terug hoeveel regels er weg zijn.

    Raakt niets anders: dit zijn losse regels zonder kledingstuk, kast of foto
    eraan, dus wissen kost alleen het overzicht zelf. Bestaat omdat een
    beheerder die een sleutel vervangt vaak ook opnieuw wil beginnen met tellen.
    """
    count = db.query(func.count(AiUsage.id)).scalar() or 0
    db.query(AiUsage).delete()
    db.commit()
    return int(count)
