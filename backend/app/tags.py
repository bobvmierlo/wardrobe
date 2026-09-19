"""Comma-separated tag columns, and the vocabularies behind them.

Garments and outfits carry several small sets of labels: which seasons they
suit, which occasions ("Werk", "Feest"), which weather, and free-form style
words ("gelaagd", "zakelijk"). SQLite has no array type and none of these is
worth a join table — nothing ever queries "every garment tagged Werk" other
than by reading the wardrobe anyway — so each is one ``TEXT`` column holding
``"Werk,Casual"``, exactly like the ``season`` column that predates all of it.

This module is the single place that knows that shape, so the rest of the app
passes lists around and never splits a string by hand.
"""

from __future__ import annotations

#: Weather a garment can be suited to. Fixed rather than admin-managed: these
#: are what :mod:`app.weather` derives from a forecast, so a label nobody can
#: produce would only ever be dead weight on the form.
WEATHER_TAGS: list[str] = [
    "Zonnig", "Bewolkt", "Regen", "Sneeuw", "Winderig", "Koud", "Mild", "Warm", "Heet",
]

#: The temperature bands above, coldest first. Kept apart from the sky
#: conditions because a recommendation weighs them differently: wearing a coat
#: in the heat is a real mistake, wearing sunny colours under a cloud is not.
TEMPERATURE_TAGS: list[str] = ["Koud", "Mild", "Warm", "Heet"]

#: Occasions seeded into the (admin-editable) list on first run.
DEFAULT_OCCASIONS: list[str] = [
    "Werk", "Casual", "Weekend", "Sport", "Avond", "Uit eten", "Feest",
    "Date", "Formeel", "Vakantie",
]

#: Style words offered as suggestions on the form. Free text underneath, so
#: anyone can type their own — this list only saves them the typing.
DEFAULT_STYLES: list[str] = [
    "Casual", "Zakelijk", "Sportief", "Klassiek", "Gelaagd", "Minimalistisch",
    "Stoer", "Chic", "Streetstyle", "Comfortabel",
]


def split_tags(value: str | None) -> list[str]:
    """``"Werk, Casual"`` → ``["Werk", "Casual"]``; blank → ``[]``."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def join_tags(values: list[str] | None) -> str | None:
    """The inverse of :func:`split_tags`, de-duplicated and order-preserving.

    Returns ``None`` rather than ``""`` for an empty list, so "no tags" is one
    value in the database instead of two that compare differently.
    """
    if not values:
        return None
    seen: dict[str, None] = {}
    for value in values:
        cleaned = (value or "").strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return ",".join(seen) or None


def normalize(value: str) -> str:
    return (value or "").strip().lower()


def overlap(tags: list[str], wanted: list[str]) -> list[str]:
    """The wanted tags this set actually has, compared case-insensitively."""
    have = {normalize(t) for t in tags}
    return [w for w in wanted if normalize(w) in have]


def has_any(value: str | None, wanted: list[str]) -> bool:
    """Whether a stored tag column mentions any of ``wanted``.

    An **untagged** item answers True: somebody who never filled the field in
    should not have their whole wardrobe filtered away. Tagging is how you
    narrow things down, not something the app makes compulsory.
    """
    tags = split_tags(value)
    if not tags or not wanted:
        return True
    return bool(overlap(tags, wanted))
