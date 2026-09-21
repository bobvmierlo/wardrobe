"""Eén zin over wat je gaat doen, omgezet in de filters van deze app.

"Zaterdag met vriendinnen naar een wijnfestival buiten in Gemert" is hoe
iemand z'n dag beschrijft. "Gelegenheid = Feest, seizoen = Zomer, weer =
Zonnig" is hoe deze app een kast doorzoekt. Deze module is de vertaling
daartussen, en verder niets.

Bewust zonder taalmodel, om dezelfde reden als de rest van :mod:`app.autofill`:
dit hoort te werken in een installatie zonder internet en zonder rekening, en
het hoort uit te leggen te zijn. Het is dus woordherkenning — een tabel met
synoniemen per gelegenheid, de maanden en seizoenen, en de weerwoorden die de
app toch al kent. Wat er niet in staat, wordt niet geraden: het resultaat zegt
altijd wát het eruit heeft gehaald, zodat het scherm dat kan tonen en iemand
het met één tik kan corrigeren in plaats van zich af te vragen waarom er
ineens alleen jassen staan.

De gelegenheden zijn door een beheerder te wijzigen, dus de namen zelf komen
uit de database; deze tabel voegt daar alleen de woorden aan toe die mensen
gebruiken in plaats van die namen.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .tags import WEATHER_TAGS

#: Woorden die op een gelegenheid wijzen, per gelegenheid zoals die standaard
#: heet. Een installatie die "Feest" heeft hernoemd of verwijderd, verliest
#: gewoon die rij — de namen uit de database winnen altijd (zie
#: :func:`interpret`).
OCCASION_WORDS: dict[str, tuple[str, ...]] = {
    "Werk": (
        "werk", "kantoor", "vergadering", "meeting", "presentatie", "sollicitatie",
        "klant", "zakelijk", "congres", "beurs",
    ),
    "Formeel": (
        "formeel", "gala", "ceremonie", "begrafenis", "uitvaart", "receptie",
        "diploma", "promotie", "black tie",
    ),
    "Feest": (
        "feest", "feestje", "bruiloft", "trouwerij", "verjaardag", "jubileum",
        "festival", "borrel", "party", "kroeg", "dansen", "concert",
    ),
    "Uit eten": ("uit eten", "restaurant", "diner", "dineren", "lunchen", "brunch"),
    "Date": ("date", "afspraakje", "romantisch"),
    "Sport": (
        "sport", "sporten", "hardlopen", "rennen", "fitness", "sportschool",
        "yoga", "zwemmen", "wandeltocht", "fietsen", "training", "wintersport",
    ),
    "Weekend": ("weekend", "zaterdag", "zondag", "vrije dag", "uitslapen"),
    "Casual": ("casual", "boodschappen", "thuis", "koffie", "relaxed", "ontspannen"),
    "Avond": ("avond", "vanavond", "'s avonds", "nacht", "uitgaan"),
    "Vakantie": (
        "vakantie", "reis", "reizen", "strand", "zee", "citytrip",
        "weekendje weg", "hotel", "kamperen",
    ),
}

#: Woorden die op een seizoen wijzen. De maanden staan erbij omdat mensen een
#: datum noemen ("in februari") in plaats van een seizoen.
SEASON_WORDS: dict[str, tuple[str, ...]] = {
    "Lente": ("lente", "voorjaar", "maart", "april", "mei", "pasen"),
    "Zomer": (
        "zomer", "juni", "juli", "augustus", "zomers", "vakantieperiode",
    ),
    "Herfst": ("herfst", "najaar", "september", "oktober", "november"),
    "Winter": (
        "winter", "december", "januari", "februari", "kerst", "oud en nieuw",
        "sinterklaas",
    ),
}

#: Woorden die op het weer wijzen. De labels zijn die van :data:`WEATHER_TAGS`,
#: want dat is waar een kast op getagd is.
WEATHER_WORDS: dict[str, tuple[str, ...]] = {
    "Zonnig": ("zon", "zonnig", "zonnetje", "onbewolkt", "strand"),
    "Bewolkt": ("bewolkt", "betrokken", "wolken", "regenachtig"),
    "Regen": ("regen", "regenachtig", "nat", "buien", "motregen", "plensbui"),
    "Sneeuw": ("sneeuw", "sneeuwt", "besneeuwd", "wintersport", "skiën", "ski"),
    "Winderig": ("wind", "winderig", "storm", "stormachtig", "waait"),
    "Koud": ("koud", "kou", "vriest", "vorst", "ijzig", "guur"),
    "Mild": ("mild", "zacht", "aangenaam", "frisjes"),
    "Warm": ("warm", "lekker weer", "zomers weer"),
    "Heet": ("heet", "hitte", "tropisch", "snikheet", "bloedheet"),
}

#: "Buiten" zegt niets over de temperatuur, maar wel dat het weer meetelt.
#: Zonder deze regel levert "buiten in de kou" hetzelfde op als "binnen".
OUTDOOR_WORDS = ("buiten", "openlucht", "terras", "tuin", "park", "veld", "kamperen")


@dataclass
class Reading:
    """Wat er uit één zin te halen viel, en wat niet."""

    occasion: str | None = None
    season: str | None = None
    weather: list[str] = field(default_factory=list)
    #: De woorden die dit opleverden, zoals ze in de zin stonden. Het scherm
    #: toont ze, zodat "waarom staat dit er?" geen raadsel is.
    matched: list[str] = field(default_factory=list)
    outdoor: bool = False

    @property
    def understood(self) -> bool:
        return bool(self.occasion or self.season or self.weather)


def _normalize(text: str) -> str:
    """Kleine letters, zonder accenten, met spaties eromheen.

    Accenten eruit omdat "skiën" en "skien" allebei worden getypt, en de
    spaties eromheen zodat een woordgrens te matchen is zonder per woord een
    reguliere expressie te bouwen.
    """
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return f" {re.sub(r'[^a-z0-9 ]+', ' ', folded)} "


#: Verbuigingen die een zelfstandig naamwoord of werkwoord in het Nederlands
#: krijgt zonder iets anders te betekenen: "koud" → "koude", "regen" →
#: "regent". Een vaste lijst, want dit is geen stemmer en hoeft dat niet te
#: zijn.
_SUFFIXES = ("", "e", "en", "s", "t", "te", "je", "tje", "de")

#: Vanaf deze lengte mag een woord ook middenin een ander woord gevonden
#: worden. Nederlands plakt samenstellingen aan elkaar ("wijnfestival",
#: "verjaardagsfeest"), en zonder dit ziet de zoeker die niet. Korter dan dit
#: wordt het gevaarlijk: "zon" zit in "zondag", en dat is een dag, geen
#: weerbericht.
_COMPOUND_MIN = 6


def _find(haystack: str, words: tuple[str, ...]) -> str | None:
    """Het eerste woord uit ``words`` dat in de zin staat.

    Heel woord (met een gewone verbuiging erachter), of — voor woorden die
    lang genoeg zijn om niet toevallig ergens in te zitten — ook als deel van
    een samenstelling.
    """
    tokens = haystack.split()
    for word in words:
        needle = _normalize(word).strip()
        if not needle:
            continue
        if " " in needle:
            # Meerdere woorden ("uit eten"): gewoon in de zin zoeken.
            if f" {needle} " in haystack:
                return word
            continue
        if len(needle) >= _COMPOUND_MIN:
            if any(needle in token for token in tokens):
                return word
            continue
        forms = {needle + suffix for suffix in _SUFFIXES}
        if any(token in forms for token in tokens):
            return word
    return None


def interpret(text: str, available_occasions: list[str] | None = None) -> Reading:
    """Lees één zin als een set filters.

    ``available_occasions`` is de lijst van deze installatie. Een naam daaruit
    die letterlijk in de zin staat wint altijd van de synoniementabel: een
    beheerder die een gelegenheid "Schoolplein" noemt, hoort die terug te zien
    als iemand "schoolplein" typt.
    """
    reading = Reading()
    haystack = _normalize(text)
    if not haystack.strip():
        return reading

    available = [o for o in (available_occasions or []) if o]
    allowed = {o.lower(): o for o in available}

    # 1. De namen van deze installatie, letterlijk.
    for name in available:
        if _find(haystack, (name,)):
            reading.occasion = name
            reading.matched.append(name.lower())
            break

    # 2. Anders de synoniemen — maar alleen voor gelegenheden die bestaan.
    if reading.occasion is None:
        for occasion, words in OCCASION_WORDS.items():
            if occasion.lower() not in allowed and available:
                continue  # deze installatie kent 'm niet; niets verzinnen
            hit = _find(haystack, words)
            if hit:
                reading.occasion = allowed.get(occasion.lower(), occasion)
                reading.matched.append(hit)
                break

    for season, words in SEASON_WORDS.items():
        hit = _find(haystack, words)
        if hit:
            reading.season = season
            reading.matched.append(hit)
            break

    for tag, words in WEATHER_WORDS.items():
        hit = _find(haystack, words)
        if hit and tag not in reading.weather:
            reading.weather.append(tag)
            reading.matched.append(hit)

    reading.outdoor = _find(haystack, OUTDOOR_WORDS) is not None
    # Alleen de tags die deze app kent, in de volgorde waarin ze op het
    # formulier staan — zodat het scherm ze net zo toont als overal elders.
    reading.weather = [t for t in WEATHER_TAGS if t in reading.weather]
    return reading
