"""A small, local colour knowledge base for suggesting outfits.

No external AI: just a curated set of colour-combination rules (the kind a
stylist would use) plus the category groups already defined for the swipe
screen. We build top + bottom (+ optional shoes / outerwear) outfits, score
each by colour harmony and season overlap, drop any pair a household member
explicitly rejected, and return the best few.
"""

from __future__ import annotations

from itertools import product

from .matching import group_of, seasons_compatible
from .models import Item
from .tags import has_any, overlap, split_tags

# Map many Dutch (and a few English) colour words onto a small base palette.
_COLOR_ALIASES: dict[str, str] = {
    "zwart": "zwart", "black": "zwart",
    "wit": "wit", "gebroken wit": "wit", "creme": "wit", "crème": "wit",
    "off-white": "wit", "white": "wit", "ecru": "wit",
    "grijs": "grijs", "antraciet": "grijs", "gray": "grijs", "grey": "grijs",
    "zilver": "grijs",
    "beige": "beige", "zand": "beige", "khaki": "beige", "kaki": "beige",
    "camel": "beige", "taupe": "beige", "bruin": "bruin", "brown": "bruin",
    "cognac": "bruin", "chocolade": "bruin",
    "blauw": "blauw", "lichtblauw": "blauw", "blue": "blauw",
    "navy": "navy", "donkerblauw": "navy", "marineblauw": "navy",
    "denim": "denim", "jeans": "denim", "spijker": "denim",
    "rood": "rood", "bordeaux": "rood", "bordeauxrood": "rood", "red": "rood",
    "wijnrood": "rood",
    "roze": "roze", "pink": "roze", "oudroze": "roze",
    "oranje": "oranje", "orange": "oranje", "terracotta": "oranje",
    "geel": "geel", "yellow": "geel", "okergeel": "geel", "oker": "geel",
    "groen": "groen", "green": "groen", "olijf": "groen", "olijfgroen": "groen",
    "legergroen": "groen", "mint": "groen",
    "paars": "paars", "purple": "paars", "lila": "paars", "violet": "paars",
    "goud": "goud", "gold": "goud",
}

# Neutrals combine with virtually anything.
_NEUTRALS = {"zwart", "wit", "grijs", "beige", "bruin", "navy", "denim"}

# Every base colour the engine understands (for the settings colour pickers).
BASE_COLORS: list[str] = sorted(set(_COLOR_ALIASES.values()))
NEUTRALS: list[str] = sorted(_NEUTRALS)

# Default pairs of non-neutral colours that are known to look good together,
# used to seed the editable rules on first run. Stored as (a, b) tuples.
DEFAULT_GOOD_PAIRS: list[tuple[str, str]] = [
    ("blauw", "bruin"), ("navy", "beige"), ("navy", "bruin"), ("denim", "wit"),
    ("rood", "navy"), ("roze", "grijs"), ("groen", "beige"), ("groen", "bruin"),
    ("oranje", "blauw"), ("geel", "blauw"), ("geel", "navy"), ("paars", "geel"),
    ("rood", "groen"), ("roze", "navy"),
]

# Default pairs that tend to clash.
DEFAULT_BAD_PAIRS: list[tuple[str, str]] = [
    ("rood", "roze"), ("rood", "oranje"), ("oranje", "roze"),
    ("groen", "oranje"), ("paars", "groen"),
]

# Fallbacks used when no DB-backed rules are passed in (e.g. direct calls).
_GOOD_PAIRS: set[frozenset[str]] = {frozenset(p) for p in DEFAULT_GOOD_PAIRS}
_BAD_PAIRS: set[frozenset[str]] = {frozenset(p) for p in DEFAULT_BAD_PAIRS}


def normalize_color(color: str | None) -> str | None:
    if not color:
        return None
    key = color.strip().lower()
    if key in _COLOR_ALIASES:
        return _COLOR_ALIASES[key]
    # Try matching any known word inside a longer description ("donkerblauwe polo").
    for word, base in _COLOR_ALIASES.items():
        if word in key:
            return base
    return None


def color_score(
    a: str | None,
    b: str | None,
    good_pairs: set[frozenset[str]] | None = None,
    bad_pairs: set[frozenset[str]] | None = None,
) -> tuple[int, str]:
    """Return (score, reason) for combining two colours.

    ``good_pairs`` / ``bad_pairs`` come from the (editable) rules; when omitted
    the built-in defaults are used so direct callers still work.
    """
    good_pairs = _GOOD_PAIRS if good_pairs is None else good_pairs
    bad_pairs = _BAD_PAIRS if bad_pairs is None else bad_pairs
    ca, cb = normalize_color(a), normalize_color(b)
    if ca is None or cb is None:
        return 1, "kleur onbekend"
    if frozenset({ca, cb}) in bad_pairs:
        return -3, f"{ca} en {cb} botsen"
    if ca == cb:
        return 2, f"ton-sur-ton {ca}"
    a_neu, b_neu = ca in _NEUTRALS, cb in _NEUTRALS
    if a_neu and b_neu:
        return 3, "neutrale tinten"
    if a_neu or b_neu:
        return 3, f"{ca if not a_neu else cb} op een neutrale basis"
    if frozenset({ca, cb}) in good_pairs:
        return 4, f"{ca} en {cb} passen mooi samen"
    return 0, f"{ca} en {cb}"


def _seasons_of(item: Item) -> set[str]:
    if not item.season:
        return set()
    return {s.strip().lower() for s in item.season.split(",") if s.strip()}


def _season_overlap(items: list[Item]) -> tuple[int, str | None]:
    sets = [_seasons_of(it) for it in items]
    sets = [s for s in sets if s and "alle seizoenen" not in s]
    if not sets:
        return 0, None
    common = set.intersection(*sets) if len(sets) > 1 else sets[0]
    if common:
        return 2, next(iter(common)).capitalize()
    return -1, None


def all_pairs(items: list[Item]) -> set[frozenset[int]]:
    """Every unordered pair of item ids in an outfit."""
    return {
        frozenset({a.id, b.id})
        for i, a in enumerate(items)
        for b in items[i + 1:]
    }


def is_combination(items: list[Item], approved_pairs: set[frozenset[int]]) -> bool:
    """Whether this outfit already exists as an approved combination.

    True once *every* pair inside it has been approved — at that point the
    outfit is no longer a suggestion but something the household already
    decided on, so it should not be offered again.
    """
    pairs = all_pairs(items)
    return bool(pairs) and pairs <= approved_pairs


#: Weather that asks for something over the top. Used both to let an outer
#: layer into a suggestion more easily and to keep one out of a warm day.
COVER_WEATHER = {"koud", "regen", "sneeuw", "winderig"}


def wants_outerwear(weather_tags: list[str] | None) -> bool:
    return any(t.lower() in COVER_WEATHER for t in (weather_tags or []))


def fits_context(
    item: Item,
    occasion: str | None = None,
    weather_tags: list[str] | None = None,
) -> bool:
    """Whether a garment belongs in an outfit for this occasion and weather.

    Untagged garments always fit — see :func:`app.tags.has_any`. A garment that
    *is* tagged has to mention the occasion asked for, and share at least one
    weather tag with the forecast.
    """
    if occasion and not has_any(item.occasion, [occasion]):
        return False
    if weather_tags and not has_any(item.weather, weather_tags):
        return False
    return True


def suggest_outfits(
    items: list[Item],
    rejected_pairs: set[frozenset[int]],
    approved_pairs: set[frozenset[int]],
    limit: int = 12,
    good_pairs: set[frozenset[str]] | None = None,
    bad_pairs: set[frozenset[str]] | None = None,
    must_include: int | None = None,
    occasion: str | None = None,
    weather_tags: list[str] | None = None,
    skip_combinations: bool = True,
) -> list[dict]:
    """Build and rank outfit suggestions from the wardrobe.

    When ``must_include`` is given, only outfits containing that item id are
    returned — used to show suggestions on a single item's page.

    ``occasion`` and ``weather_tags`` narrow the wardrobe before anything is
    combined: with them, only garments tagged for that occasion and that
    weather (or tagged with nothing at all) take part, and an outer layer is
    added readily when it is cold, wet or windy and left out when it is not.

    Outfits the household already settled are left out entirely: a pair anyone
    rejected is never combined, and an outfit whose every pair is approved is
    dropped because it is a combination already, not a suggestion.

    ``skip_combinations=False`` keeps that last group. The swipe screen wants
    them gone — it is looking for things still to decide — but "maak looks van
    mijn kast" wants exactly the opposite: a combination the household already
    approved is the *best* candidate for a saved look, not a disqualified one.
    """
    good_pairs = _GOOD_PAIRS if good_pairs is None else good_pairs
    bad_pairs = _BAD_PAIRS if bad_pairs is None else bad_pairs

    def cscore(a: str | None, b: str | None) -> tuple[int, str]:
        return color_score(a, b, good_pairs, bad_pairs)

    by_group: dict[str, list[Item]] = {}
    for it in items:
        if not fits_context(it, occasion, weather_tags):
            continue
        by_group.setdefault(group_of(it.category), []).append(it)

    tops = by_group.get("top", []) + by_group.get("dress", [])
    bottoms = by_group.get("bottom", [])
    shoes = by_group.get("shoes", [])
    outer = by_group.get("outerwear", [])

    def pair_ok(a: Item, b: Item) -> bool:
        # Never combine explicitly rejected pairs, nor items that can't share
        # a season (e.g. a pure winter piece with a pure summer one).
        return (
            frozenset({a.id, b.id}) not in rejected_pairs
            and seasons_compatible(a.season, b.season)
        )

    results: list[dict] = []
    # Dresses need no separate bottom; treat them as a full base.
    bottom_choices = bottoms or [None]  # allow tops-only if nothing else

    for top, bottom in product(tops, bottom_choices):
        base = [top]
        score = 0
        reasons: list[str] = []
        if bottom is not None:
            if group_of(top.category) == "dress":
                continue  # a dress already covers top+bottom
            if not pair_ok(top, bottom):
                continue
            s, why = cscore(top.color, bottom.color)
            score += s
            reasons.append(why)
            if frozenset({top.id, bottom.id}) in approved_pairs:
                # This pair is settled, but the outfit as a whole is not (fully
                # approved outfits are dropped below), so say so precisely.
                score += 3
                reasons.append("deels al goedgekeurd")
            base.append(bottom)

        # Optionally add the best-matching shoe.
        best_shoe = None
        best_shoe_score = 0
        for sh in shoes:
            if any(not pair_ok(sh, b) for b in base):
                continue
            ss = sum(cscore(sh.color, b.color)[0] for b in base)
            if ss > best_shoe_score:
                best_shoe, best_shoe_score = sh, ss
        if best_shoe is not None:
            base.append(best_shoe)
            score += max(best_shoe_score, 0)

        # Optionally add outerwear when it clearly fits.
        best_outer = None
        best_outer_score = 0
        for ow in outer:
            if any(not pair_ok(ow, b) for b in base):
                continue
            os_ = sum(cscore(ow.color, b.color)[0] for b in base)
            if os_ > best_outer_score:
                best_outer, best_outer_score = ow, os_
        # How readily an outer layer joins depends on the weather: on a cold or
        # wet day a coat belongs there even if its colour is only adequate, and
        # on a warm one it does not belong there at all.
        cover = wants_outerwear(weather_tags)
        threshold = 0 if cover else len(base)
        if weather_tags and not cover:
            best_outer = None
        if best_outer is not None and best_outer_score >= threshold:
            base.append(best_outer)
            score += max(best_outer_score // len(base), 0)
            if cover:
                score += 2
                reasons.append("met een laag eroverheen voor dit weer")

        season_score, season_name = _season_overlap(base)
        score += season_score
        if season_name:
            reasons.append(f"geschikt voor {season_name}")

        # A garment explicitly tagged for this occasion or this weather is a
        # better answer than one that merely was not ruled out.
        if occasion and all(overlap(split_tags(it.occasion), [occasion]) for it in base):
            score += 3
            reasons.append(f"gekleed voor {occasion.lower()}")
        if weather_tags:
            tagged = [it for it in base if overlap(split_tags(it.weather), weather_tags)]
            if tagged:
                score += min(len(tagged), 3)

        settled = is_combination(base, approved_pairs)
        if settled:
            if skip_combinations:
                continue  # already an approved combination, not a suggestion
            # Kept, so say what it is: not "partly" approved but wholly so,
            # and worth putting near the top.
            reasons = [r for r in reasons if r != "deels al goedgekeurd"]
            reasons.append("een al goedgekeurde combinatie")
            score += 3

        reason = ", ".join(dict.fromkeys(r for r in reasons if r)) or "combinatie"
        results.append({"items": base, "score": score, "reason": reason.capitalize()})

    # Best first; de-duplicate on the set of item ids.
    results.sort(key=lambda r: r["score"], reverse=True)
    seen: set[frozenset[int]] = set()
    unique: list[dict] = []
    for r in results:
        if must_include is not None and not any(it.id == must_include for it in r["items"]):
            continue
        key = frozenset(it.id for it in r["items"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
        if len(unique) >= limit:
            break
    return unique
