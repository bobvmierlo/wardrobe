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


#: The sky conditions, as opposed to the temperature bands above. Everything in
#: :data:`WEATHER_TAGS` is one or the other.
SKY_TAGS: list[str] = [t for t in WEATHER_TAGS if t not in TEMPERATURE_TAGS]

#: Which skies each temperature band can be worn in.
#:
#: The asymmetry between the two halves of the vocabulary is the whole point.
#: A temperature band is a property of the clothes — a winter coat is for cold
#: weather and stays wrong on a hot day, whatever the sky does. A sky is not:
#: you put a coat *over* the outfit when it rains, and the jumper and jeans
#: underneath are the same jumper and jeans they were on a dry day. So an
#: outfit that suits a temperature suits every sky that temperature happens in,
#: and the only exclusions here are the ones the weather itself makes: it does
#: not snow when it is warm, and "Heet" is not a cloudy afternoon.
SKY_BY_TEMPERATURE: dict[str, tuple[str, ...]] = {
    "Koud": ("Zonnig", "Bewolkt", "Regen", "Sneeuw", "Winderig"),
    "Mild": ("Zonnig", "Bewolkt", "Regen", "Winderig"),
    "Warm": ("Zonnig", "Bewolkt", "Winderig"),
    "Heet": ("Zonnig",),
}


def temperatures(tags: list[str]) -> list[str]:
    """Just the temperature bands out of a set of weather tags."""
    return overlap(tags, TEMPERATURE_TAGS)


def skies(tags: list[str]) -> list[str]:
    """Just the sky conditions out of a set of weather tags."""
    return overlap(tags, SKY_TAGS)


def implied_skies(tags: list[str]) -> list[str]:
    """Every sky the temperatures in ``tags`` can occur in.

    Empty when there is no temperature to reason from: guessing a sky off
    nothing would be inventing, and an empty weather column already means "no
    objection" everywhere in the app (see :func:`has_any`).
    """
    found: list[str] = []
    for temperature in temperatures(tags):
        for sky in SKY_BY_TEMPERATURE.get(temperature, ()):
            if sky not in found:
                found.append(sky)
    return [tag for tag in WEATHER_TAGS if tag in found]


def with_implied_skies(tags: list[str]) -> list[str]:
    """``tags`` plus the skies those temperatures can be worn in.

    What an outfit gets tagged with. Without this a jumper-and-jeans that both
    say "Koud" comes out as a look for cold weather *and nothing else*, so the
    planner calls it unsuitable the moment it rains — which is exactly the day
    you would wear it, with a coat on top. Tags already on the outfit are kept
    in the vocabulary's own order, so the result reads the same way the form
    offers it.
    """
    if not tags:
        return []
    keep = {normalize(t) for t in [*tags, *implied_skies(tags)]}
    return [tag for tag in WEATHER_TAGS if normalize(tag) in keep]
