"""Category grouping used to suggest sensible combinations first.

Two items from *different* groups (e.g. a top and a trousers) are more
interesting to judge than two items from the same group, so the swipe screen
surfaces cross-group pairs first.
"""

GROUPS: dict[str, set[str]] = {
    "top": {
        "polo", "t-shirt", "tshirt", "shirt", "overhemd", "blouse", "trui",
        "vest", "hoodie", "sweater", "sweatshirt", "top",
    },
    "bottom": {"broek", "jeans", "chino", "pantalon", "shorts", "korte broek", "rok"},
    "outerwear": {"jas", "blazer", "colbert", "bodywarmer", "gilet", "mantel", "vest jas"},
    "shoes": {"schoenen", "sneakers", "laarzen", "boots", "sandalen"},
    "dress": {"jurk", "jumpsuit", "pak"},
    "accessory": {"riem", "sjaal", "muts", "pet", "das", "stropdas", "sokken", "tas"},
}

_CATEGORY_TO_GROUP: dict[str, str] = {
    cat: group for group, cats in GROUPS.items() for cat in cats
}


def group_of(category: str) -> str:
    return _CATEGORY_TO_GROUP.get((category or "").strip().lower(), "other")


def is_cross_group(cat_a: str, cat_b: str) -> bool:
    return group_of(cat_a) != group_of(cat_b)


# Upper-body garments ("bovenkleding") that pair with a bottom on the swipe.
_UPPER_GROUPS: set[str] = {"top", "outerwear"}


def is_upper(category: str) -> bool:
    """Whether this is bovenkleding: a top, or a jacket/blazer."""
    return group_of(category) in _UPPER_GROUPS


def is_bottom(category: str) -> bool:
    """Whether this is een onderstuk: broek, jeans, rok, ..."""
    return group_of(category) == "bottom"


def can_combine(cat_a: str, cat_b: str) -> bool:
    """Whether two garments may be offered as a pair on the swipe screen.

    The swipe judges outfits, and an outfit is always an upper-body garment
    (bovenkleding: a top, or a jacket/blazer) with a bottom (broek/rok). So a
    pair is only shown when exactly one item is a bottom and the other is upper
    wear. This rules out polo-with-polo, broek-with-broek, jacket-with-top and
    everything else (shoes, accessories, ...).
    """
    return (is_upper(cat_a) and is_bottom(cat_b)) or (is_upper(cat_b) and is_bottom(cat_a))


_ALL_SEASONS = "alle seizoenen"


def _season_set(season: str | None) -> set[str]:
    if not season:
        return set()
    return {s.strip().lower() for s in season.split(",") if s.strip()}


def seasons_compatible(season_a: str | None, season_b: str | None) -> bool:
    """Whether two garments can be worn in a shared season.

    Items with no season set, or tagged "Alle seizoenen", match anything.
    Otherwise the two must share at least one season, so a pure winter item
    is never suggested next to a pure summer one.
    """
    sa, sb = _season_set(season_a), _season_set(season_b)
    if not sa or not sb:
        return True
    if _ALL_SEASONS in sa or _ALL_SEASONS in sb:
        return True
    return bool(sa & sb)
