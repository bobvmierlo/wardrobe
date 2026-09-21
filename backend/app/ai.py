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
huisgenoten. Staat de laag uit — de standaard — dan wordt er niets verstuurd en bestaat
deze module praktisch niet. Aanzetten kan een beheerder in de app, of de
operator met ``WARDROBE_AI_*`` in de omgeving; wat in de omgeving staat wint en
staat in de app op slot (zie :func:`app.app_settings.ai_config`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .app_settings import AiConfig
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


@dataclass
class AiCall:
    """Eén verzoek dat de deur uit ging, en hoeveel tokens het kostte.

    Deze module schrijft niets naar de database — hij weet niet eens dat er een
    is. Wie 'm aanroept geeft een lijst mee, krijgt 'm gevuld terug en bewaart
    'm zelf (zie :mod:`app.ai_usage`). Zo blijft "praten met Anthropic" en
    "bijhouden wat dat kost" van elkaar gescheiden, en blijft een test op deze
    module een test zonder sessie.
    """
    purpose: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def _count(usage, *names: str) -> int:
    """Het eerste veld van ``usage`` dat bestaat en een getal is, of 0.

    Meerdere namen omdat de SDK ze door de jaren heen anders heeft genoemd, en
    een ontbrekend veld hier niets ergers mag zijn dan een nul in de teller.
    """
    for name in names:
        value = getattr(usage, name, None)
        if isinstance(value, int):
            return value
    return 0


def is_configured(config: AiConfig) -> bool:
    """Of deze installatie de AI-laag überhaupt mag gebruiken."""
    return config.usable


def _client(config: AiConfig):
    """De Anthropic-client. Een functie, zodat een test 'm kan vervangen."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - afhankelijkheid ontbreekt
        raise AiUnavailable(
            "De AI-laag staat aan, maar het pakket 'anthropic' is niet"
            " geïnstalleerd in dit image."
        ) from exc
    return anthropic.Anthropic(
        api_key=config.api_key.strip(),
        timeout=config.timeout_seconds,
        max_retries=1,
    )


def _ask(
    config: AiConfig,
    system: str,
    prompt: str,
    schema: dict,
    max_tokens: int,
    purpose: str = "",
    usage: list[AiCall] | None = None,
) -> dict:
    """Eén vraag, één JSON-antwoord in de gevraagde vorm.

    Het enige punt in deze module dat het netwerk op gaat, zodat een test er
    één functie voor hoeft te vervangen — dezelfde opzet als
    :func:`app.weather._get_json`.

    Ging het verzoek eruit, dan komt er een :class:`AiCall` in ``usage`` te
    staan, ook als het antwoord daarna onbruikbaar blijkt: het is verstuurd en
    het wordt dus gefactureerd, en een teller die alleen de geslaagde keren
    telt vertelt precies het verkeerde verhaal over de rekening.
    """
    client = _client(config)
    request = {
        "model": config.model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        # Het schema dwingt de vórm af; de waarden worden hieronder alsnog
        # tegen onze eigen lijsten gehouden. Lage effort: dit is invulwerk,
        # geen redeneerwerk.
        "output_config": {
            "format": {"type": "json_schema", "schema": schema},
            "effort": config.effort,
        },
    }

    try:
        if config.refusal_fallback:
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

    if usage is not None:
        counts = getattr(response, "usage", None)
        usage.append(
            AiCall(
                purpose=purpose,
                # Wat er terugkomt, niet wat we vroegen: bij een weigering kan
                # het terugvalmodel geantwoord hebben, en dat heeft z'n eigen
                # tarief.
                model=str(getattr(response, "model", "") or config.model),
                input_tokens=_count(counts, "input_tokens"),
                output_tokens=_count(counts, "output_tokens"),
                cache_read_tokens=_count(counts, "cache_read_input_tokens"),
                cache_write_tokens=_count(counts, "cache_creation_input_tokens"),
            )
        )

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
    config: AiConfig,
    items: list,
    occasions: list[str],
    weather_tags: list[str],
    usage: list[AiCall] | None = None,
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
    answer = _ask(
        config, TAG_SYSTEM, prompt, TAG_SCHEMA, max_tokens=8000,
        purpose="tags", usage=usage,
    )

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


def name_looks(
    config: AiConfig, looks: list[list], usage: list[AiCall] | None = None
) -> dict[int, str]:
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
    answer = _ask(
        config, NAME_SYSTEM, prompt, NAME_SCHEMA, max_tokens=4000,
        purpose="names", usage=usage,
    )

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


# ---------------------------------------------------------------------------
# Looks laten samenstellen
# ---------------------------------------------------------------------------

COMPOSE_SYSTEM = (
    "Je stelt outfits samen uit de kledingkast van één persoon. Je krijgt de"
    " kledingstukken, welke combinaties de bewoners zelf al hebben goedgekeurd,"
    " welke ze hebben afgekeurd, en welke outfits al bestaan."
    "\n\nRegels:"
    "\n- Gebruik uitsluitend de meegegeven id's. Verzin er nooit een bij."
    "\n- Een afgekeurd paar mag NOOIT samen in één outfit. Dit is de"
    " belangrijkste regel: de bewoners hebben dat zelf besloten."
    "\n- Goedgekeurde paren zijn juist een aanrader; gebruik ze waar het past."
    "\n- Een outfit is een bovenstuk met een onderstuk, of een jurk, meestal met"
    " schoenen erbij, en eventueel een jas of accessoire. Twee broeken of twee"
    " truien samen is geen outfit."
    "\n- Herhaal geen outfit die al bestaat, en maak ze onderling gevarieerd:"
    " niet elk kledingstuk in elke outfit."
    "\n- Kies tags alleen uit de meegegeven lijsten, en alleen als ze voor"
    " élk kledingstuk in de outfit kloppen. Twijfel je, laat ze leeg."
    "\n- Temperatuur en lucht zijn niet hetzelfde soort weer. Of een outfit bij"
    " 'Koud', 'Mild', 'Warm' of 'Heet' past, bepaalt de kleding zelf. Of het"
    " regent, sneeuwt, waait of bewolkt is, bepaalt de kleding niet: daar gaat"
    " een jas overheen. Noem dus gerust 'Regen' of 'Winderig' bij een outfit"
    " die bij die temperatuur past — dat maakt 'm niet ongeschikt."
    "\n- Geef elke outfit een korte Nederlandse naam van maximaal vier woorden."
    "\n- Antwoord uitsluitend met JSON in het gevraagde formaat."
)

COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "outfits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "naam": {"type": "string"},
                    "item_ids": {"type": "array", "items": {"type": "integer"}},
                    "occasions": {"type": "array", "items": {"type": "string"}},
                    "weather": {"type": "array", "items": {"type": "string"}},
                    "reden": {"type": "string"},
                },
                "required": ["naam", "item_ids", "occasions", "weather", "reden"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["outfits"],
    "additionalProperties": False,
}


@dataclass
class AiLook:
    """Eén voorstel van het model, al opgeschoond maar nog niet gecontroleerd.

    Wat hier uit komt is nadrukkelijk een *voorstel*: of het mag, bepaalt
    :func:`app.autofill.validate_ai_looks` aan de hand van de oordelen die in
    de database staan.
    """
    name: str
    item_ids: list[int]
    occasions: list[str]
    weather: list[str]
    reason: str = ""


def compose_looks(
    config: AiConfig,
    items: list,
    approved_pairs: set[frozenset[int]],
    rejected_pairs: set[frozenset[int]],
    existing: set[frozenset[int]],
    occasions: list[str],
    weather_tags: list[str],
    count: int,
    usage: list[AiCall] | None = None,
) -> list[AiLook]:
    """Vraag het model om outfits samen te stellen uit deze kast.

    De goedgekeurde en afgekeurde paren gaan mee, zodat het model er rekening
    mee kán houden. Dat het er rekening mee *moet* houden wordt daarna pas
    afgedwongen — een model dat zich vergist, mag nooit een besluit van de
    bewoners overrulen.
    """
    if not items:
        return []
    subset = items[:MAX_ITEMS]
    known = {item.id for item in subset}

    def _pairs(pairs: set[frozenset[int]]) -> list[list[int]]:
        # Alleen paren waarvan beide stukken ook echt meegaan, anders staan er
        # id's in de vraag die in de lijst ontbreken.
        out = []
        for pair in pairs:
            ids = sorted(pair)
            if len(ids) == 2 and ids[0] in known and ids[1] in known:
                out.append(ids)
        return sorted(out)[:400]

    prompt = json.dumps(
        {
            "aantal_gevraagd": count,
            "gelegenheden": occasions,
            "weertypes": weather_tags,
            "kledingstukken": [describe_item(item) for item in subset],
            "goedgekeurde_paren": _pairs(approved_pairs),
            "afgekeurde_paren": _pairs(rejected_pairs),
            "bestaande_outfits": [sorted(ids) for ids in list(existing)[:100]],
        },
        ensure_ascii=False,
        indent=1,
    )
    answer = _ask(
        config, COMPOSE_SYSTEM, prompt, COMPOSE_SCHEMA, max_tokens=8000,
        purpose="looks", usage=usage,
    )

    proposals: list[AiLook] = []
    for row in answer.get("outfits", []) or []:
        if not isinstance(row, dict):
            continue
        ids = row.get("item_ids")
        if not isinstance(ids, list):
            continue
        cleaned_ids: list[int] = []
        for value in ids:
            if isinstance(value, int) and value in known and value not in cleaned_ids:
                cleaned_ids.append(value)
        name = row.get("naam")
        name = " ".join(name.split())[:MAX_NAME].strip() if isinstance(name, str) else ""
        reason = row.get("reden")
        reason = " ".join(reason.split())[:200].strip() if isinstance(reason, str) else ""
        if len(cleaned_ids) < 2:
            continue  # niets om een outfit van te maken
        proposals.append(
            AiLook(
                name=name,
                item_ids=cleaned_ids,
                occasions=_keep(row.get("occasions"), {o.lower(): o for o in occasions}),
                weather=_keep(row.get("weather"), {w.lower(): w for w in weather_tags}),
                reason=reason,
            )
        )
    return proposals
