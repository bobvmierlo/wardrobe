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

# Pairs of non-neutral colours that are known to look good together. Stored
# unordered (frozenset) so lookup is direction-independent.
_GOOD_PAIRS: set[frozenset[str]] = {
    frozenset({"blauw", "bruin"}),
    frozenset({"navy", "beige"}),
    frozenset({"navy", "bruin"}),
    frozenset({"denim", "wit"}),
    frozenset({"rood", "navy"}),
    frozenset({"roze", "grijs"}),
    frozenset({"groen", "beige"}),
    frozenset({"groen", "bruin"}),
    frozenset({"oranje", "blauw"}),
    frozenset({"geel", "blauw"}),
    frozenset({"geel", "navy"}),
    frozenset({"paars", "geel"}),
    frozenset({"blauw", "geel"}),
    frozenset({"rood", "groen"}),
    frozenset({"roze", "navy"}),
}

# Pairs that tend to clash.
_BAD_PAIRS: set[frozenset[str]] = {
    frozenset({"rood", "roze"}),
    frozenset({"rood", "oranje"}),
    frozenset({"oranje", "roze"}),
    frozenset({"groen", "oranje"}),
    frozenset({"paars", "groen"}),
}


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


def color_score(a: str | None, b: str | None) -> tuple[int, str]:
    """Return (score, reason) for combining two colours."""
    ca, cb = normalize_color(a), normalize_color(b)
    if ca is None or cb is None:
        return 1, "kleur onbekend"
    if frozenset({ca, cb}) in _BAD_PAIRS:
        return -3, f"{ca} en {cb} botsen"
    if ca == cb:
        return 2, f"ton-sur-ton {ca}"
    a_neu, b_neu = ca in _NEUTRALS, cb in _NEUTRALS
    if a_neu and b_neu:
        return 3, "neutrale tinten"
    if a_neu or b_neu:
        return 3, f"{ca if not a_neu else cb} op een neutrale basis"
    if frozenset({ca, cb}) in _GOOD_PAIRS:
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


def suggest_outfits(
    items: list[Item],
    rejected_pairs: set[frozenset[int]],
    approved_pairs: set[frozenset[int]],
    limit: int = 12,
) -> list[dict]:
    """Build and rank outfit suggestions from the wardrobe."""
    by_group: dict[str, list[Item]] = {}
    for it in items:
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
            s, why = color_score(top.color, bottom.color)
            score += s
            reasons.append(why)
            if frozenset({top.id, bottom.id}) in approved_pairs:
                score += 3
                reasons.append("al goedgekeurd")
            base.append(bottom)

        # Optionally add the best-matching shoe.
        best_shoe = None
        best_shoe_score = 0
        for sh in shoes:
            if any(not pair_ok(sh, b) for b in base):
                continue
            ss = sum(color_score(sh.color, b.color)[0] for b in base)
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
            os_ = sum(color_score(ow.color, b.color)[0] for b in base)
            if os_ > best_outer_score:
                best_outer, best_outer_score = ow, os_
        if best_outer is not None and best_outer_score >= len(base):
            base.append(best_outer)
            score += max(best_outer_score // len(base), 0)

        season_score, season_name = _season_overlap(base)
        score += season_score
        if season_name:
            reasons.append(f"geschikt voor {season_name}")

        reason = ", ".join(dict.fromkeys(r for r in reasons if r)) or "combinatie"
        results.append({"items": base, "score": score, "reason": reason.capitalize()})

    # Best first; de-duplicate on the set of item ids.
    results.sort(key=lambda r: r["score"], reverse=True)
    seen: set[frozenset[int]] = set()
    unique: list[dict] = []
    for r in results:
        key = frozenset(it.id for it in r["items"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
        if len(unique) >= limit:
            break
    return unique
