"""De optionele AI-laag: alleen waar de regels niets te zeggen hebben.

:mod:`app.autofill` doet dit werk zonder enige externe dienst, en dat blijft de
standaard. Deze module is een *laag erbovenop*, die een beheerder aanzet, en de
taakverdeling is met opzet scherp:

* **De regels bepalen wat mag.** Welke kledingstukken samen mogen (niemand
  keurde het paar af), welke kleuren kunnen (de kleurregels van deze
  installatie), welke gelegenheden bestaan. Daar komt het model niet aan.
* **Het model vult in waar geen regel bestaat.** De gelegenheid van een
  kledingstuk waar de categorie niets over zegt, en een naam voor een look die
  leuker leest dan "Wit overhemd met nette broek".

Alles wat terugkomt wordt daarna nog eens langs de eigen woordenlijsten
gehaald: een tag die deze installatie niet kent, wordt weggegooid. Het model
kan dus nooit een gelegenheid introduceren die een beheerder heeft verwijderd,
en nooit een kledingstuk aan een look toevoegen dat er niet in zat.

**Wat er de deur uit gaat**, en alleen als iemand de knop met AI gebruikt: de
naam, categorie, kleur, maat en seizoenen van de betrokken kledingstukken.
Geen foto's, geen namen van personen, geen kastnamen, geen oordelen van
huisgenoten. Staat ``WARDROBE_AI_ENABLED`` uit — de standaard — dan wordt er
niets verstuurd en bestaat deze module praktisch niet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .config import settings
from .logging_setup import get_logger

log = get_logger("ai")

#: Hoeveel kledingstukken er hooguit in één verzoek gaan. Een kast van
#: tweehonderd stuks past ruim binnen het contextvenster, maar een bodemloze
#: lijst is een rekening die niemand heeft zien aankomen.
MAX_ITEMS = 120

#: Hoeveel looks er hooguit in één keer een naam krijgen.
MAX_LOOKS = 40


class AiUnavailable(Exception):
    """Aanroepen kon niet. Draagt een zin die getoond mag worden."""


def is_configured() -> bool:
    """Of deze installatie de AI-laag überhaupt mag gebruiken."""
    return bool(settings.ai_enabled and settings.ai_api_key.strip())


def _client():
    """De Anthropic-client. Een functie, zodat een test 'm kan vervangen."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - afhankelijkheid ontbreekt
        raise AiUnavailable(
            "De AI-laag staat aan, maar het pakket 'anthropic' is niet"
            " geïnstalleerd in dit image."
        ) from exc
    return anthropic.Anthropic(
        api_key=settings.ai_api_key.strip(),
        timeout=settings.ai_timeout_seconds,
        max_retries=1,
    )


def _ask(system: str, prompt: str, schema: dict, max_tokens: int) -> dict:
    """Eén vraag, één JSON-antwoord in de gevraagde vorm.

    Het enige punt in deze module dat het netwerk op gaat, zodat een test er
    één functie voor hoeft te vervangen — dezelfde opzet als
    :func:`app.weather._get_json`.
    """
    client = _client()
    request = {
        "model": settings.ai_model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        # Het schema dwingt de vórm af; de waarden worden hieronder alsnog
        # tegen onze eigen lijsten gehouden. Lage effort: dit is invulwerk,
        # geen redeneerwerk.
        "output_config": {
            "format": {"type": "json_schema", "schema": schema},
            "effort": settings.ai_effort,
        },
    }

    try:
        if settings.ai_refusal_fallback:
            # Weigert het model de vraag, dan draait dezelfde vraag binnen
            # hetzelfde verzoek op een terugvalmodel. Kost niets zolang het
            # niet gebeurt, en scheelt een mislukte knop als het wel gebeurt.
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **request,
            )
        else:
            response = client.messages.create(**request)
    except Exception as exc:  # noqa: BLE001 - alles hier is "de knop doet niets"
        log.warning("AI-verzoek mislukt: %s", exc)
        raise AiUnavailable(
            "De AI-dienst antwoordde niet. De app heeft het zonder gedaan."
        ) from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise AiUnavailable("De AI-dienst wilde deze vraag niet beantwoorden.")

    text = next(
        (block.text for block in response.content if getattr(block, "type", "") == "text"),
        "",
    )
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AiUnavailable("De AI-dienst gaf een onbegrijpelijk antwoord.") from exc
    if not isinstance(parsed, dict):
        raise AiUnavailable("De AI-dienst gaf een onverwacht antwoord.")
    return parsed


# ---------------------------------------------------------------------------
# Tags raden waar de regels zwijgen
# ---------------------------------------------------------------------------

TAG_SYSTEM = (
    "Je helpt bij het labelen van een kledingkast. Je krijgt kledingstukken met"
    " naam, categorie, kleur en seizoen, en twee vaste woordenlijsten. Kies per"
    " kledingstuk uitsluitend woorden uit die lijsten."
    "\n\nRegels:"
    "\n- Gebruik alleen exact de aangeboden woorden; verzin er nooit een bij."
    "\n- Twijfel je, laat de lijst dan leeg. Een ontbrekend label is beter dan"
    " een verkeerd label."
    "\n- Antwoord uitsluitend met JSON in het gevraagde formaat."
)

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "occasions": {"type": "array", "items": {"type": "string"}},
                    "weather": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "occasions", "weather"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass
class AiTags:
    """Wat het model voorstelt voor één kledingstuk, al gefilterd."""
    item_id: int
    occasions: list[str]
    weather: list[str]


def describe_item(item) -> dict:
    """Wat er van een kledingstuk de deur uit gaat. Nadrukkelijk niet meer."""
    return {
        "id": item.id,
        "naam": item.name,
        "categorie": item.category,
        "kleur": item.color or "",
        "seizoen": item.season or "",
    }


def suggest_tags(
    items: list,
    occasions: list[str],
    weather_tags: list[str],
) -> list[AiTags]:
    """Vraag het model om gelegenheid- en weertags voor deze kledingstukken.

    Geeft alleen terug wat door de eigen woordenlijsten komt, en alleen voor
    kledingstukken die ook echt zijn meegestuurd.
    """
    if not items:
        return []
    subset = items[:MAX_ITEMS]
    known_ids = {item.id for item in subset}
    allowed_occasions = {o.lower(): o for o in occasions}
    allowed_weather = {w.lower(): w for w in weather_tags}

    prompt = json.dumps(
        {
            "gelegenheden": occasions,
            "weertypes": weather_tags,
            "kledingstukken": [describe_item(item) for item in subset],
        },
        ensure_ascii=False,
        indent=1,
    )
    answer = _ask(TAG_SYSTEM, prompt, TAG_SCHEMA, max_tokens=8000)

    results: list[AiTags] = []
    for row in answer.get("items", []) or []:
        if not isinstance(row, dict):
            continue
        item_id = row.get("id")
        if not isinstance(item_id, int) or item_id not in known_ids:
            continue  # een id dat we niet stuurden hoort hier niet te zijn
        picked = AiTags(
            item_id=item_id,
            occasions=_keep(row.get("occasions"), allowed_occasions),
            weather=_keep(row.get("weather"), allowed_weather),
        )
        if picked.occasions or picked.weather:
            results.append(picked)
    return results


def _keep(values, allowed: dict[str, str]) -> list[str]:
    """Alleen wat deze installatie kent, in de spelling die zij gebruikt."""
    if not isinstance(values, list):
        return []
    kept: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        canonical = allowed.get(value.strip().lower())
        if canonical and canonical not in kept:
            kept.append(canonical)
    return kept


# ---------------------------------------------------------------------------
# Namen voor looks die de app al heeft samengesteld
# ---------------------------------------------------------------------------

NAME_SYSTEM = (
    "Je verzint korte Nederlandse namen voor outfits. Je krijgt per outfit de"
    " kledingstukken die erin zitten."
    "\n\nRegels:"
    "\n- Maximaal vier woorden, geen aanhalingstekens, geen emoji."
    "\n- Beschrijvend en nuchter; geen reclametaal."
    "\n- Elke naam is anders dan de andere in dezelfde lijst."
    "\n- Antwoord uitsluitend met JSON in het gevraagde formaat."
)

NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "namen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "naam": {"type": "string"},
                },
                "required": ["index", "naam"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["namen"],
    "additionalProperties": False,
}

#: Langer dan dit wordt afgekapt: de kolom in de lijst is niet oneindig, en de
#: databasekolom is 120 tekens.
MAX_NAME = 60


def name_looks(looks: list[list]) -> dict[int, str]:
    """Een naam per samengestelde look, op volgorde van binnenkomst.

    ``looks`` is een lijst van lijsten kledingstukken. Wat terugkomt is een
    afbeelding van index naar naam; indexen die het model oversloeg of die
    onbruikbaar terugkwamen, staan er niet in — de aanroeper houdt dan gewoon
    de naam die de app zelf had bedacht.
    """
    if not looks:
        return {}
    subset = looks[:MAX_LOOKS]
    prompt = json.dumps(
        {
            "outfits": [
                {
                    "index": index,
                    "kledingstukken": [describe_item(item) for item in items],
                }
                for index, items in enumerate(subset)
            ]
        },
        ensure_ascii=False,
        indent=1,
    )
    answer = _ask(NAME_SYSTEM, prompt, NAME_SCHEMA, max_tokens=4000)

    names: dict[int, str] = {}
    used: set[str] = set()
    for row in answer.get("namen", []) or []:
        if not isinstance(row, dict):
            continue
        index, name = row.get("index"), row.get("naam")
        if not isinstance(index, int) or not (0 <= index < len(subset)):
            continue
        if not isinstance(name, str):
            continue
        cleaned = " ".join(name.split())[:MAX_NAME].strip()
        # Een lege of dubbele naam is geen verbetering, dus die valt af en het
        # voorstel van de app zelf blijft staan.
        if not cleaned or cleaned.lower() in used:
            continue
        used.add(cleaned.lower())
        names[index] = cleaned
    return names
