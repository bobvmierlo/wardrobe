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
