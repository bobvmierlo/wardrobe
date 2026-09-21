"""The actual weather, and what it means for what you put on.

Two free services, neither of which needs an account or an API key:

* **Open-Meteo** for the forecast, and for looking a place up by name.
* **PDOK's Locatieserver** (the Dutch Kadaster's own address service) for
  looking a place up by a Dutch postcode, which Open-Meteo's geocoder does not
  do at all.
* **Zippopotam** for a postcode in any other country — it is built on the
  GeoNames postal data, which covers most of the world but, notably, not the
  Netherlands.

Both are called by the *server*, never by the browser. That is not an
accident: the app's own Content-Security-Policy says ``connect-src 'self'``,
so a page that talked to api.open-meteo.com directly would simply be blocked —
and proxying it here means one shared cache instead of one request per open
tab, and no third party learning the coordinates of everyone's home from their
browser.

What comes back is turned into the same small vocabulary garments are tagged
with (:data:`app.tags.WEATHER_TAGS`), because that is the only form the
recommendation engine can compare against a wardrobe.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import httpx

from .config import settings
from .logging_setup import get_logger
from .tags import TEMPERATURE_TAGS

log = get_logger("weather")

DEFAULT_TIMEOUT = 8.0

#: Above this (km/h) it is windy enough to change what you would wear over it.
WINDY_KMH = 30.0

#: Temperature bands, in °C, applied to the *apparent* temperature — what it
#: feels like outside is what decides whether you take a coat, not what the
#: thermometer says in the shade.
COLD_BELOW = 8.0
MILD_BELOW = 18.0
WARM_BELOW = 26.0

#: WMO weather interpretation codes → (Dutch description, our sky tag).
#: Open-Meteo answers in these codes; the table is the whole published set,
#: so an unexpected one means the service changed, not that we guessed short.
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Onbewolkt", "Zonnig"),
    1: ("Overwegend onbewolkt", "Zonnig"),
    2: ("Half bewolkt", "Bewolkt"),
    3: ("Bewolkt", "Bewolkt"),
    45: ("Mistig", "Bewolkt"),
    48: ("Mist met rijp", "Bewolkt"),
    51: ("Lichte motregen", "Regen"),
    53: ("Motregen", "Regen"),
    55: ("Dichte motregen", "Regen"),
    56: ("Lichte ijzel", "Regen"),
    57: ("IJzel", "Regen"),
    61: ("Lichte regen", "Regen"),
    63: ("Regen", "Regen"),
    65: ("Zware regen", "Regen"),
    66: ("Lichte ijsregen", "Regen"),
    67: ("IJsregen", "Regen"),
    71: ("Lichte sneeuwval", "Sneeuw"),
    73: ("Sneeuw", "Sneeuw"),
    75: ("Zware sneeuwval", "Sneeuw"),
    77: ("Sneeuwkorrels", "Sneeuw"),
    80: ("Lichte buien", "Regen"),
    81: ("Buien", "Regen"),
    82: ("Zware buien", "Regen"),
    85: ("Lichte sneeuwbuien", "Sneeuw"),
    86: ("Sneeuwbuien", "Sneeuw"),
    95: ("Onweer", "Regen"),
    96: ("Onweer met hagel", "Regen"),
    99: ("Zwaar onweer met hagel", "Regen"),
}


class WeatherUnavailable(Exception):
    """The forecast could not be fetched. Carries a message fit to show."""


@dataclass
class Place:
    """Somewhere you can ask the weather for."""
    name: str
    latitude: float
    longitude: float
    region: str | None = None
    country: str | None = None
    postcode: str | None = None

    @property
    def label(self) -> str:
        """The one-line name shown in the app, e.g. "Gemert, Noord-Brabant"."""
        parts = [self.name]
        if self.region and self.region != self.name:
            parts.append(self.region)
        elif self.country:
            parts.append(self.country)
        return ", ".join(parts)


@dataclass
class Forecast:
    """The weather right now, plus the rest of today."""
    temperature: float
    apparent_temperature: float
    wind_speed: float
    precipitation: float
    code: int
    description: str
    tags: list[str] = field(default_factory=list)
    high: float | None = None
    low: float | None = None
    precipitation_chance: int | None = None
    is_day: bool = True
    location: str = ""
    latitude: float = 0.0
    longitude: float = 0.0

    @property
    def summary(self) -> str:
        """One sentence, the way the app says it out loud."""
        return f"{self.description}, {round(self.temperature)}°C"


#: Hoe iemand temperatuur beleeft, als verschuiving in graden op de banden
#: hierboven. Vijf stappen in plaats van drie, omdat de uitersten echt bestaan:
#: er zijn mensen die bij vijftien graden nog in korte broek lopen, en mensen
#: die daar een jas bij aantrekken. Eén schaal voor beide.
#:
#: Positief = jij vindt het eerder warm dan de thermometer zegt.
TEMPERATURE_PREFERENCES: tuple[tuple[int, str, str], ...] = (
    (-6, "Echte kouwkleum", "Ik heb het bijna altijd eerder koud dan anderen."),
    (-3, "Snel koud", "Ik trek eerder een extra laag aan."),
    (0, "Gemiddeld", "Gewoon zoals de weersverwachting het zegt."),
    (3, "Snel warm", "Ik heb het eerder warm dan anderen."),
    (6, "Echt warmbloedig", "Bij een graad of vijftien kan ik nog in korte broek."),
)

MIN_OFFSET = min(offset for offset, _label, _hint in TEMPERATURE_PREFERENCES)
MAX_OFFSET = max(offset for offset, _label, _hint in TEMPERATURE_PREFERENCES)


def clamp_offset(offset: int | None) -> int:
    """Houd een voorkeur binnen de schaal, wat er ook is opgeslagen."""
    if offset is None:
        return 0
    return max(MIN_OFFSET, min(MAX_OFFSET, int(offset)))


def temperature_tag(apparent_c: float, offset: int = 0) -> str:
    """De temperatuurband waarin dit weer valt, voor deze persoon.

    ``offset`` verschuift de banden in plaats van de thermometer: de app blijft
    vijftien graden vijftien graden noemen, maar iemand die het snel warm heeft
    krijgt daar "Warm" bij te zien en dus ook korte mouwen voorgesteld. Dat is
    precies het verschil dat niemand uit een weerbericht kan aflezen, en dat
    per persoon dertig graden aan kledingkeuze scheelt.
    """
    felt = apparent_c + clamp_offset(offset)
    if felt < COLD_BELOW:
        return "Koud"
    if felt < MILD_BELOW:
        return "Mild"
    if felt < WARM_BELOW:
        return "Warm"
    return "Heet"


def bares_arms_and_legs(apparent_c: float, offset: int = 0) -> bool:
    """Of een korte broek en korte mouwen hierbij nog kunnen, voor deze persoon.

    De grens tussen "Mild" en "Warm": daaronder trekt vrijwel niemand nog iets
    korts aan, daarboven vrijwel iedereen wel.
    """
    return apparent_c + clamp_offset(offset) >= MILD_BELOW


def tags_for(code: int, apparent_c: float, wind_kmh: float, offset: int = 0) -> list[str]:
    """The wardrobe tags a given forecast comes down to.

    Always a sky condition and exactly one temperature band, plus "Winderig"
    when the wind is worth dressing for. Order matters only for how it reads.
    """
    _, sky = WMO_CODES.get(int(code), ("Onbekend", "Bewolkt"))
    tags = [sky, temperature_tag(apparent_c, offset)]
    if wind_kmh >= WINDY_KMH:
        tags.append("Winderig")
    return tags


def retag(forecast: "Forecast", offset: int = 0) -> "Forecast":
    """Dezelfde verwachting, met de banden van déze persoon erop.

    De verwachting zelf wordt per locatie gedeeld en gecachet — hij is voor
    iedereen gelijk. Alleen wat je eruit afleidt is persoonlijk, dus dat gebeurt
    hier, op het laatste moment, in plaats van in de cache.
    """
    if not clamp_offset(offset):
        return forecast
    return Forecast(
        **{
            **forecast.__dict__,
            "tags": tags_for(
                forecast.code, forecast.apparent_temperature, forecast.wind_speed, offset
            ),
        }
    )


def describe(code: int) -> str:
    return WMO_CODES.get(int(code), ("Onbekend weer", "Bewolkt"))[0]


# ---------------------------------------------------------------------------
# Talking to the services
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict) -> dict:
    """One GET, one JSON body. A function so the tests can replace it."""
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url, params=params, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        # A 404 from the postcode service just means "no such postcode", which
        # the caller turns into an empty result rather than an error.
        raise WeatherUnavailable(f"De weerdienst antwoordde met {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        log.warning("Weerdienst onbereikbaar (%s): %s", url, exc)
        raise WeatherUnavailable("De weerdienst is nu niet bereikbaar") from exc
    except ValueError as exc:  # not JSON
        raise WeatherUnavailable("De weerdienst gaf een onbegrijpelijk antwoord") from exc


#: Forecasts, keyed by rounded coordinates. Two people in one household asking
#: on the same morning is one request, not two — and Open-Meteo's free tier is
#: a gift that should not be leaned on.
_cache: dict[tuple[float, float], tuple[float, Forecast]] = {}


def _cache_seconds() -> float:
    return max(0, settings.weather_cache_minutes) * 60


def clear_cache() -> None:
    _cache.clear()
    _daily_cache.clear()


_POSTCODE_RE = re.compile(r"^\s*(\d{4})\s*([a-zA-Z]{0,2})\s*$")

#: "POINT(5.6889 51.5583)" — how PDOK writes a coordinate. Longitude first,
#: which is the opposite order from everything else in this module.
_POINT_RE = re.compile(r"POINT\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.IGNORECASE)


def search_places(query: str, limit: int = 8) -> list[Place]:
    """Places matching a typed name or postcode.

    A Dutch-style postcode ("5420", "5421 AB") goes to a postcode service,
    which knows them; everything else is a name and goes to the geocoder. A
    postcode that turns up nothing falls through to the name search, so typing
    a foreign postcode still has a chance of working.
    """
    query = (query or "").strip()
    if not query:
        return []
    if not settings.weather_enabled:
        raise WeatherUnavailable("Het weer staat uit in deze installatie")

    postcode = _POSTCODE_RE.match(query)
    if postcode:
        digits, letters = postcode.group(1), postcode.group(2).upper()
        places = _search_postcode(digits, letters)
        if places:
            return places[:limit]
    return _search_name(query, limit)


def _search_postcode(digits: str, letters: str = "") -> list[Place]:
    """A postcode, from whichever service knows the country we are in.

    Two services because one of them does not cover this app's own country.
    Zippopotam is built on the GeoNames postal data, which does not include
    the Netherlands — ``api.zippopotam.us/nl/5421`` is a 404, and always was.
    That failure was silent: the lookup fell through to the name search, the
    name search made nothing of four digits either, and typing your own
    postcode simply returned no results.

    So a Dutch postcode goes to PDOK's Locatieserver instead — the Kadaster's
    own, open, keyless address service — and everywhere else keeps using
    Zippopotam, which is good at exactly that.
    """
    country = (settings.weather_country or "nl").strip().lower()
    if country == "nl":
        return _search_postcode_nl(digits, letters)
    return _search_postcode_zippopotam(country, digits)


def _search_postcode_nl(digits: str, letters: str = "") -> list[Place]:
    """A Dutch postcode via PDOK's Locatieserver.

    The full "5421 AB" narrows it to one street; the four digits on their own
    to a town, which is all the weather needs anyway. Both are asked for the
    same way, and the answers are folded down to one entry per town: twenty
    streets in the same place is not twenty choices to a person picking where
    they live.
    """
    query = f"{digits} {letters}".strip()
    try:
        data = _get_json(
            settings.pdok_api_url,
            {"q": query, "fq": "type:postcode", "rows": 25},
        )
    except WeatherUnavailable:
        return []

    places: list[Place] = []
    seen: set[str] = set()
    for doc in ((data.get("response") or {}).get("docs") or []):
        if not isinstance(doc, dict):
            continue
        point = _POINT_RE.search(str(doc.get("centroide_ll") or ""))
        town = (doc.get("woonplaatsnaam") or "").strip()
        if point is None or not town:
            continue
        if town.lower() in seen:
            continue
        seen.add(town.lower())
        try:
            places.append(
                Place(
                    name=town,
                    # PDOK writes POINT(lon lat); everything else here is
                    # (lat, lon), and swapping them lands you in the sea.
                    latitude=float(point.group(2)),
                    longitude=float(point.group(1)),
                    region=(doc.get("provincienaam") or "").strip() or None,
                    country="Nederland",
                    postcode=(doc.get("postcode") or "").strip() or query,
                )
            )
        except (TypeError, ValueError):
            continue
    return places


def _search_postcode_zippopotam(country: str, code: str) -> list[Place]:
    """A postcode anywhere Zippopotam has data for. Never the Netherlands."""
    url = f"{settings.postcode_api_url.rstrip('/')}/{country}/{code}"
    try:
        data = _get_json(url, {})
    except WeatherUnavailable:
        # Unknown postcode, or the service is down. Either way the name search
        # is a better answer than an error page.
        return []
    places = []
    for entry in data.get("places", []) or []:
        try:
            places.append(
                Place(
                    name=entry.get("place name") or code,
                    latitude=float(entry["latitude"]),
                    longitude=float(entry["longitude"]),
                    region=entry.get("state"),
                    country=data.get("country"),
                    postcode=data.get("post code") or code,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return places


def _search_name(query: str, limit: int) -> list[Place]:
    data = _get_json(
        settings.geocoding_api_url,
        {"name": query, "count": limit, "language": "nl", "format": "json"},
    )
    places = []
    for entry in data.get("results", []) or []:
        try:
            places.append(
                Place(
                    name=entry["name"],
                    latitude=float(entry["latitude"]),
                    longitude=float(entry["longitude"]),
                    region=entry.get("admin1"),
                    country=entry.get("country"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return places


def current(latitude: float, longitude: float, label: str = "") -> Forecast:
    """The weather at these coordinates, from the cache when it is fresh."""
    if not settings.weather_enabled:
        raise WeatherUnavailable("Het weer staat uit in deze installatie")

    key = (round(float(latitude), 2), round(float(longitude), 2))
    cached = _cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _cache_seconds():
        forecast = cached[1]
        # The coordinates are the cache key, not the name somebody gave them:
        # two people can call the same spot "thuis" and "Gemert".
        return _relabel(forecast, label)

    data = _get_json(
        settings.weather_api_url,
        {
            "latitude": key[0],
            "longitude": key[1],
            "current": (
                "temperature_2m,apparent_temperature,precipitation,"
                "weather_code,wind_speed_10m,is_day"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,weather_code"
            ),
            "timezone": "auto",
            "forecast_days": 1,
            "wind_speed_unit": "kmh",
        },
    )
    forecast = _parse(data, key[0], key[1])
    _cache[key] = (time.monotonic(), forecast)
    return _relabel(forecast, label)


def _relabel(forecast: Forecast, label: str) -> Forecast:
    if not label or forecast.location == label:
        return forecast
    return Forecast(**{**forecast.__dict__, "location": label})


def _parse(data: dict, latitude: float, longitude: float) -> Forecast:
    current_block = data.get("current") or {}
    daily = data.get("daily") or {}

    def _first(key: str):
        values = daily.get(key) or []
        return values[0] if values else None

    def _number(value, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    code = int(_number(current_block.get("weather_code"), 3))
    temperature = _number(current_block.get("temperature_2m"))
    apparent = _number(current_block.get("apparent_temperature"), temperature)
    wind = _number(current_block.get("wind_speed_10m"))
    chance = _first("precipitation_probability_max")

    return Forecast(
        temperature=temperature,
        apparent_temperature=apparent,
        wind_speed=wind,
        precipitation=_number(current_block.get("precipitation")),
        code=code,
        description=describe(code),
        tags=tags_for(code, apparent, wind),
        high=None if _first("temperature_2m_max") is None else _number(_first("temperature_2m_max")),
        low=None if _first("temperature_2m_min") is None else _number(_first("temperature_2m_min")),
        precipitation_chance=None if chance is None else int(_number(chance)),
        is_day=bool(current_block.get("is_day", 1)),
        latitude=latitude,
        longitude=longitude,
    )


def manual_forecast(tags: list[str], label: str = "Handmatig ingesteld") -> Forecast:
    """A stand-in forecast for someone who would rather say it themselves.

    Not everybody wants to hand over a location, and a server without internet
    access cannot fetch one anyway. The tags are all the recommendation engine
    ever reads, so a hand-picked set works exactly as well as a fetched one —
    it just cannot fill in a temperature, and says so by leaving it at the
    middle of whichever band was chosen.
    """
    bands = {"Koud": 4.0, "Mild": 13.0, "Warm": 22.0, "Heet": 29.0}
    chosen = next((t for t in tags if t in TEMPERATURE_TAGS), "Mild")
    sky = next((t for t in tags if t in {"Zonnig", "Bewolkt", "Regen", "Sneeuw"}), "Bewolkt")
    temperature = bands[chosen]
    return Forecast(
        temperature=temperature,
        apparent_temperature=temperature,
        wind_speed=WINDY_KMH if "Winderig" in tags else 0.0,
        precipitation=0.0,
        code={"Zonnig": 0, "Bewolkt": 3, "Regen": 63, "Sneeuw": 73}[sky],
        description=sky,
        tags=list(dict.fromkeys(tags)) or [sky, chosen],
        location=label,
    )


@dataclass
class DayForecast:
    """One day's outlook, for planning a week ahead."""
    day: str  # "JJJJ-MM-DD"
    code: int
    description: str
    high: float | None
    low: float | None
    wind_speed: float
    precipitation_chance: int | None
    tags: list[str] = field(default_factory=list)


#: Daily outlooks, cached like the current weather and keyed the same way.
_daily_cache: dict[tuple[float, float, int], tuple[float, list[DayForecast]]] = {}

#: How far out a forecast is worth showing. Open-Meteo answers for sixteen
#: days; anything past a week is a guess dressed up as a number, and the week
#: planner only ever asks for seven.
MAX_FORECAST_DAYS = 7


def retag_day(day: "DayForecast", offset: int = 0) -> "DayForecast":
    """Eén dag uit de vooruitblik, met de banden van deze persoon."""
    if not clamp_offset(offset):
        return day
    feels = day.high if day.high is not None else 12.0
    return DayForecast(
        **{**day.__dict__, "tags": tags_for(day.code, float(feels), day.wind_speed, offset)}
    )


def daily(latitude: float, longitude: float, days: int = MAX_FORECAST_DAYS) -> list[DayForecast]:
    """The outlook for the next few days at these coordinates.

    Tagged off the day's *warmest* apparent temperature and strongest wind:
    what you get dressed for in the morning is the day ahead of you, not the
    average of it.
    """
    if not settings.weather_enabled:
        raise WeatherUnavailable("Het weer staat uit in deze installatie")

    days = max(1, min(int(days), MAX_FORECAST_DAYS))
    key = (round(float(latitude), 2), round(float(longitude), 2), days)
    cached = _daily_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _cache_seconds():
        return cached[1]

    data = _get_json(
        settings.weather_api_url,
        {
            "latitude": key[0],
            "longitude": key[1],
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "apparent_temperature_max,precipitation_probability_max,"
                "wind_speed_10m_max"
            ),
            "timezone": "auto",
            "forecast_days": days,
            "wind_speed_unit": "kmh",
        },
    )
    block = data.get("daily") or {}
    dates = block.get("time") or []
    out: list[DayForecast] = []

    def _at(name: str, index: int):
        values = block.get(name) or []
        return values[index] if index < len(values) else None

    for index, day in enumerate(dates):
        try:
            code = int(_at("weather_code", index) or 3)
        except (TypeError, ValueError):
            code = 3
        high = _at("temperature_2m_max", index)
        low = _at("temperature_2m_min", index)
        apparent = _at("apparent_temperature_max", index)
        wind = _at("wind_speed_10m_max", index) or 0.0
        chance = _at("precipitation_probability_max", index)
        feels = float(apparent if apparent is not None else (high if high is not None else 12.0))
        out.append(
            DayForecast(
                day=str(day),
                code=code,
                description=describe(code),
                high=None if high is None else float(high),
                low=None if low is None else float(low),
                wind_speed=float(wind),
                precipitation_chance=None if chance is None else int(chance),
                tags=tags_for(code, feels, float(wind)),
            )
        )

    _daily_cache[key] = (time.monotonic(), out)
    return out
