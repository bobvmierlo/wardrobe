"""«Je zou dit aan kunnen trekken.»

Given the weather outside and (optionally) what you are going out for, rank
what is in the wardrobe. Two sources feed one list:

* **saved outfits** — sets somebody already decided on, tagged with the
  weather and occasions they suit. These win by default: a human already said
  these clothes go together.
* **fresh combinations** — built by :mod:`app.suggestions` from garments that
  fit the same context, so a wardrobe with no saved outfits yet still gets an
  answer on day one.

Every recommendation carries the sentences that produced it. A suggestion you
cannot argue with is a suggestion you cannot correct, and this app has always
told people *why* two things were put together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Item, Outfit
from .suggestions import normalize_color, wants_outerwear
from .tags import TEMPERATURE_TAGS, overlap, split_tags

#: Worn in the last few days: suggested last, so a week does not become the
#: same three outfits. Only ever applied to people who keep a wear log.
RECENT_DAYS = 3
STALE_DAYS = 10


@dataclass
class Recommendation:
    """One thing to wear, and the case for it."""
    items: list[Item]
    score: int
    reasons: list[str] = field(default_factory=list)
    outfit: Outfit | None = None
    #: "saved" (an outfit you put together before) or "new" (built just now).
    source: str = "new"
    last_worn: str | None = None

    @property
    def reason(self) -> str:
        return ", ".join(dict.fromkeys(r for r in self.reasons if r)) or "past bij vandaag"


def _sky_tags(tags: list[str]) -> list[str]:
    return [t for t in tags if t not in TEMPERATURE_TAGS]


def score_outfit(
    outfit: Outfit,
    weather_tags: list[str],
    occasion: str | None,
    season: str | None = None,
) -> tuple[int, list[str]]:
    """How well a saved outfit answers today, and why.

    The temperature band carries the most weight by a distance. Being caught
    out in the cold is a real mistake; wearing the wrong shade of grey under a
    cloud is not, so a sky mismatch never outvotes a temperature match.
    """
    score = 0
    reasons: list[str] = []

    outfit_weather = split_tags(outfit.weather)
    if outfit_weather and weather_tags:
        bands = [t for t in weather_tags if t in TEMPERATURE_TAGS]
        outfit_bands = [t for t in outfit_weather if t in TEMPERATURE_TAGS]
        matched_band = overlap(outfit_bands, bands)
        if matched_band:
            score += 6
            reasons.append(f"gemaakt voor {matched_band[0].lower()} weer")
        elif outfit_bands:
            # Tagged for a different temperature altogether: a summer outfit on
            # a winter morning is the one thing this screen must not propose.
            score -= 8
        matched_sky = overlap(outfit_weather, _sky_tags(weather_tags))
        if matched_sky:
            score += 3
            reasons.append(f"past bij {matched_sky[0].lower()} weer")
        if "Winderig" in weather_tags and "Winderig" in outfit_weather:
            score += 1

    outfit_occasions = split_tags(outfit.occasion)
    if occasion:
        if overlap(outfit_occasions, [occasion]):
            score += 6
            reasons.append(f"geschikt voor {occasion.lower()}")
        elif outfit_occasions:
            score -= 6  # tagged for other occasions; this is not its moment

    if season:
        outfit_seasons = split_tags(outfit.season)
        if outfit_seasons and overlap(outfit_seasons, [season]):
            score += 2
            reasons.append(f"een {season.lower()}-outfit")

    return score, reasons


def _profile_bonus(
    items: list[Item],
    style_colors: list[str],
    style_words: list[str],
) -> tuple[int, list[str]]:
    """Extra weight for an outfit in this person's own palette and words."""
    score = 0
    reasons: list[str] = []
    if style_colors:
        wanted = {c.lower() for c in style_colors}
        hits = sum(1 for it in items if (normalize_color(it.color) or "") in wanted)
        if hits:
            score += min(hits, 3)
            reasons.append("in je eigen kleuren")
    if style_words:
        tags: list[str] = []
        for it in items:
            tags.extend(split_tags(it.style))
        matched = overlap(tags, style_words)
        if matched:
            score += min(len(matched), 3)
            reasons.append(f"jouw stijl: {matched[0].lower()}")
    return score, reasons


def _recency(last_worn: str | None, today: date) -> tuple[int, list[str]]:
    """Nudge away from what you wore yesterday, towards what hangs unused."""
    if last_worn is None:
        return 2, ["nog niet eerder gedragen"]
    try:
        worn = date.fromisoformat(last_worn)
    except ValueError:
        return 0, []
    days = (today - worn).days
    if days <= 0:
        return -10, ["vandaag al gedragen"]
    if days <= RECENT_DAYS:
        return -5, [f"{days} dag(en) geleden gedragen"]
    if days >= STALE_DAYS:
        return 2, ["al een tijd niet gedragen"]
    return 0, []


def rank_saved(
    outfits: list[Outfit],
    weather_tags: list[str],
    occasion: str | None,
    season: str | None = None,
    last_worn: dict[int, str] | None = None,
    style_colors: list[str] | None = None,
    style_words: list[str] | None = None,
    today: date | None = None,
) -> list[Recommendation]:
    """Rank outfits somebody already saved. Best first."""
    today = today or date.today()
    last_worn = last_worn or {}
    results: list[Recommendation] = []

    for outfit in outfits:
        items = outfit.items
        if not items:
            continue
        score, reasons = score_outfit(outfit, weather_tags, occasion, season)
        bonus, why = _profile_bonus(items, style_colors or [], style_words or [])
        score += bonus
        reasons += why
        worn = last_worn.get(outfit.id)
        recency, why = _recency(worn, today)
        score += recency
        reasons += why
        # Saved outfits start ahead of freshly built ones: somebody already
        # looked at these clothes together and said yes.
        score += 5
        results.append(
            Recommendation(
                items=items,
                score=score,
                reasons=reasons,
                outfit=outfit,
                source="saved",
                last_worn=worn,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def bare_skin_note(
    apparent_c: float | None,
    offset: int,
) -> str | None:
    """De zin die zegt of een korte broek er voor jóu nog in zit.

    Bestaat omdat dit precies het stukje is dat een weerbericht niet kan
    zeggen: bij vijftien graden loopt de een in korte broek en trekt de ander
    een jas aan. Alleen de moeite waard als de persoonlijke voorkeur er
    daadwerkelijk iets aan verandert — anders is het een open deur.
    """
    from .weather import bares_arms_and_legs, clamp_offset

    if apparent_c is None:
        return None
    offset = clamp_offset(offset)
    if not offset:
        return None

    personal = bares_arms_and_legs(apparent_c, offset)
    average = bares_arms_and_legs(apparent_c, 0)
    if personal == average:
        return None  # jouw voorkeur maakt hier geen verschil

    degrees = round(apparent_c)
    if personal:
        return (
            f"Bij {degrees}° houdt bijna iedereen z'n benen bedekt, maar jij hebt"
            " het snel warm — korte broek en korte mouwen kunnen voor jou prima."
        )
    return (
        f"Bij {degrees}° gaan de meeste mensen in korte mouwen, maar jij hebt het"
        " snel koud — hou het lekker bedekt."
    )


def weather_advice(forecast_tags: list[str], temperature: float | None = None) -> str:
    """The one-line nudge above the suggestions."""
    if "Regen" in forecast_tags:
        return "Het wordt nat — denk aan een jas die tegen een bui kan."
    if "Sneeuw" in forecast_tags:
        return "Sneeuw op komst — laagjes en stevige schoenen."
    if "Koud" in forecast_tags:
        return "Koud vandaag — een warme buitenlaag is geen overbodige luxe."
    if "Heet" in forecast_tags:
        return "Het wordt heet — hou het licht en luchtig."
    if "Winderig" in forecast_tags:
        return "Stevige wind — iets dat niet opwaait draagt prettiger."
    if "Zonnig" in forecast_tags and "Warm" in forecast_tags:
        return "Zonnig en aangenaam — een prima dag voor iets lichters."
    return "Niks bijzonders aan het weer — je kunt alle kanten op."


def should_add_layer(forecast_tags: list[str]) -> bool:
    return wants_outerwear(forecast_tags)


def week_days(start: date, count: int = 7) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]
