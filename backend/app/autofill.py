"""Filling in a wardrobe that was never tagged, and building looks out of it.

Two jobs, both on request and both for the same situation: a kast that has been
in use for a while, full of garments nobody ever tagged and with no saved looks
at all. Without tags the recommendations have nothing to go on, and asking
somebody to go through two hundred garments by hand is asking them not to.

Neither job invents anything it cannot defend:

* **Tagging** only ever fills a field that is *empty*, and only where the
  category (and failing that the season) makes the answer obvious. A winter
  coat is for cold weather; whether a pair of jeans is "Werk" depends on the
  person, so it is left alone. A wrong tag is worse than no tag, because an
  empty field never excludes a garment and a wrong one does.
* **Composing looks** uses the same scoring the rest of the app uses — the
  installation's own colour rules, season overlap, and never a pair anybody
  rejected. The tags on a look are read off the garments in it, so a look
  claims nothing its clothes do not.

Both are reversible by hand: a tag can be cleared on the garment's own page, a
look deleted from Looks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .matching import group_of
from .models import Item
from .suggestions import normalize_color, suggest_outfits
from .tags import join_tags, split_tags

#: Weather that follows from what a garment *is*. Matched as substrings against
#: the category **and the name**, the way :mod:`app.matching` matches
#: categories, because both are free text and the detail usually sits in the
#: name: the category is "Jas" and the garment is called "Winterjas" or
#: "Regenjas". The tables run from specific to general and the first hit wins,
#: so a name can only ever make the answer sharper than the category alone.
WEATHER_BY_CATEGORY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("winterjas", "parka", "mantel", "regenjas"), ("Koud", "Regen", "Winderig")),
    (("jas",), ("Koud", "Winderig")),
    (("bodywarmer", "gilet"), ("Koud", "Winderig")),
    (("coltrui", "trui", "hoodie", "sweater", "vest"), ("Koud", "Mild")),
    (("laars", "boot"), ("Koud", "Regen")),
    (("muts", "sjaal", "handschoen"), ("Koud", "Winderig")),
    (("shorts", "korte broek", "short"), ("Warm", "Heet", "Zonnig")),
    (("sandaal", "slipper"), ("Warm", "Heet")),
    (("tanktop", "hemd", "t-shirt", "tshirt", "polo"), ("Mild", "Warm")),
    (("overhemd", "blouse"), ("Mild", "Warm")),
    (("blazer", "colbert"), ("Mild",)),
    (("pet", "zonnehoed"), ("Zonnig", "Warm")),
)

#: What a season says about the weather, for garments whose category says
#: nothing. Deliberately thin: a season is a much weaker signal than a coat.
WEATHER_BY_SEASON: dict[str, tuple[str, ...]] = {
    "winter": ("Koud",),
    "herfst": ("Mild", "Koud"),
    "lente": ("Mild",),
    "zomer": ("Warm", "Heet"),
}

#: Occasions that follow from the category. Much shorter than the weather table
#: on purpose — whether a garment is "work" is a question about the person's
#: job, not about the garment, so only the unambiguous ones are here.
OCCASION_BY_CATEGORY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("blazer", "colbert", "pantalon"), ("Werk", "Formeel")),
    (("overhemd", "blouse"), ("Werk", "Casual")),
    (("hoodie", "sweater", "joggingbroek", "trainingsbroek"), ("Casual", "Weekend")),
    (("t-shirt", "tshirt", "jeans", "sneaker", "shorts"), ("Casual", "Weekend")),
)


def _describe(item: Item) -> str:
    """The text the tables are matched against: the category and the name."""
    return f"{item.category or ''} {item.name or ''}".lower()


def _first_match(
    text: str, table: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
) -> tuple[str, ...]:
    """The first row whose words occur in the text. Order is the priority.

    "Winterjas" has to meet the winter-coat row before the plain "jas" row, so
    the tables are ordered from specific to general and the first hit wins.
    """
    for words, tags in table:
        if any(word in text for word in words):
            return tags
    return ()


def weather_for(item: Item) -> list[str]:
    """The weather tags this garment obviously suits, or ``[]`` when unclear."""
    tags = list(_first_match(_describe(item), WEATHER_BY_CATEGORY))
    if tags:
        return tags
    # Nothing from the category; fall back to the seasons it was given.
    seasons = {s.lower() for s in split_tags(item.season)}
    from_season: list[str] = []
    for season, values in WEATHER_BY_SEASON.items():
        if season in seasons:
            from_season.extend(values)
    return list(dict.fromkeys(from_season))


def occasions_for(item: Item, available: list[str]) -> list[str]:
    """Occasions that follow from the category, limited to ones that exist.

    ``available`` is the installation's own list: if a beheerder removed
    "Formeel", this must not put it back on two hundred garments.
    """
    allowed = {a.lower(): a for a in available}
    return [
        allowed[tag.lower()]
        for tag in _first_match(_describe(item), OCCASION_BY_CATEGORY)
        if tag.lower() in allowed
    ]


@dataclass
class TagPlan:
    """What tagging would do to one garment."""
    item: Item
    weather: list[str] = field(default_factory=list)
    occasions: list[str] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return bool(self.weather or self.occasions)


def plan_tags(items: list[Item], available_occasions: list[str]) -> list[TagPlan]:
    """Work out what could be filled in, without changing anything.

    A field that already has something in it is never touched — not even to add
    to it. Somebody who tagged a garment has said what they think, and this
    routine is a guess.
    """
    plans: list[TagPlan] = []
    for item in items:
        plan = TagPlan(item=item)
        if not split_tags(item.weather):
            plan.weather = weather_for(item)
        if not split_tags(item.occasion):
            plan.occasions = occasions_for(item, available_occasions)
        if plan.changes:
            plans.append(plan)
    return plans


def apply_tags(plans: list[TagPlan]) -> int:
    """Write a plan onto the garments. Returns how many were changed."""
    for plan in plans:
        if plan.weather:
            plan.item.weather = join_tags(plan.weather)
        if plan.occasions:
            plan.item.occasion = join_tags(plan.occasions)
    return len(plans)


# ---------------------------------------------------------------------------
# Composing looks
# ---------------------------------------------------------------------------

#: An outfit is skipped when this much of it is already in a look built in this
#: same run. Without it the best-scoring garment ends up in every single look.
OVERLAP_LIMIT = 0.5


@dataclass
class LookPlan:
    """One look this would create."""
    name: str
    items: list[Item]
    seasons: list[str] = field(default_factory=list)
    occasions: list[str] = field(default_factory=list)
    weather: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    reason: str = ""


def _shared(items: list[Item], attribute: str) -> list[str]:
    """Tags every *tagged* garment in the outfit agrees on.

    An intersection rather than a union, because these decide when the look can
    be worn: a look is only for the rain if nothing in it objects to rain.
    Garments with nothing filled in do not get a vote — the same rule the rest
    of the app uses for an untagged garment.
    """
    sets = [set(split_tags(getattr(item, attribute))) for item in items]
    sets = [s for s in sets if s]
    if not sets:
        return []
    common = set.intersection(*sets)
    # Keep the order they appear in, so the result reads the way it was typed.
    ordered: list[str] = []
    for item in items:
        for tag in split_tags(getattr(item, attribute)):
            if tag in common and tag not in ordered:
                ordered.append(tag)
    return ordered


def _union(items: list[Item], attribute: str) -> list[str]:
    """Every tag anything in the outfit carries — for descriptive tags only."""
    ordered: list[str] = []
    for item in items:
        for tag in split_tags(getattr(item, attribute)):
            if tag not in ordered:
                ordered.append(tag)
    return ordered


def _name_for(items: list[Item], taken: set[str]) -> str:
    """A name that says what the look is, and is not already in use.

    Built from the garments themselves rather than something generic: "Wit
    overhemd met nette broek" tells you what it is in the list; "Look 7" does
    not.
    """
    by_group: dict[str, Item] = {}
    for item in items:
        by_group.setdefault(group_of(item.category), item)

    top = by_group.get("dress") or by_group.get("top") or by_group.get("outerwear")
    bottom = by_group.get("bottom")
    if top is not None and bottom is not None and group_of(top.category) != "dress":
        base = f"{top.name} met {bottom.name}"
    elif top is not None:
        base = top.name
    else:
        base = items[0].name

    base = base[:110].strip()
    name = base
    suffix = 2
    while name.lower() in taken:
        name = f"{base} ({suffix})"
        suffix += 1
    taken.add(name.lower())
    return name


def _overlap(items: list[Item], used: set[int]) -> float:
    if not items:
        return 1.0
    return sum(1 for item in items if item.id in used) / len(items)


def plan_looks(
    items: list[Item],
    rejected_pairs: set[frozenset[int]],
    approved_pairs: set[frozenset[int]],
    existing: set[frozenset[int]],
    taken_names: set[str],
    count: int,
    good_pairs: set[frozenset[str]] | None = None,
    bad_pairs: set[frozenset[str]] | None = None,
) -> list[LookPlan]:
    """Compose up to ``count`` looks from the wardrobe, without saving anything.

    ``existing`` holds the garment sets of the looks already saved, so running
    this twice does not produce the same looks again.
    """
    # Ask for far more than we need: most candidates are dropped for overlapping
    # with one already picked, which is what keeps the results varied.
    pool = suggest_outfits(
        items,
        rejected_pairs,
        approved_pairs,
        limit=max(count * 8, 40),
        good_pairs=good_pairs,
        bad_pairs=bad_pairs,
    )

    plans: list[LookPlan] = []
    used: set[int] = set()
    # Two passes: the first keeps the looks varied, the second fills up the
    # remainder if the wardrobe is too small to be fussy about it.
    for limit in (OVERLAP_LIMIT, 1.0):
        for candidate in pool:
            if len(plans) >= count:
                break
            chosen: list[Item] = candidate["items"]
            key = frozenset(item.id for item in chosen)
            if key in existing:
                continue
            if _overlap(chosen, used) > limit:
                continue
            existing.add(key)
            used.update(item.id for item in chosen)
            plans.append(
                LookPlan(
                    name=_name_for(chosen, taken_names),
                    items=chosen,
                    seasons=_shared(chosen, "season"),
                    occasions=_shared(chosen, "occasion"),
                    weather=_shared(chosen, "weather"),
                    styles=_union(chosen, "style"),
                    reason=candidate["reason"],
                )
            )
        if len(plans) >= count:
            break
    return plans


def palette_of(items: list[Item]) -> list[str]:
    """The base colours in an outfit, for explaining a look in one line."""
    colors: list[str] = []
    for item in items:
        base = normalize_color(item.color)
        if base and base not in colors:
            colors.append(base)
    return colors


# ---------------------------------------------------------------------------
# Voorstellen van de AI toetsen aan wat de bewoners hebben besloten
# ---------------------------------------------------------------------------

@dataclass
class LookReview:
    """Wat er met de voorstellen van het model gebeurde, en waarom.

    Bestaat zodat het scherm kan zeggen wat er is weggegooid in plaats van
    stilletjes minder looks op te leveren dan het model voorstelde.
    """
    accepted: list[LookPlan] = field(default_factory=list)
    rejected_pair: int = 0
    already_existed: int = 0
    too_small: int = 0
    duplicate: int = 0

    @property
    def dropped(self) -> int:
        return self.rejected_pair + self.already_existed + self.too_small + self.duplicate

    def summary(self) -> str | None:
        """Eén zin voor het scherm, of None als alles door de keuring kwam."""
        if not self.dropped:
            return None
        parts = []
        if self.rejected_pair:
            parts.append(
                f"{self.rejected_pair} met een combinatie die iemand had afgekeurd"
            )
        if self.already_existed:
            parts.append(f"{self.already_existed} die al bestond")
        if self.duplicate:
            parts.append(f"{self.duplicate} dubbel")
        if self.too_small:
            parts.append(f"{self.too_small} zonder bruikbare kleding")
        return f"{self.dropped} voorstel(len) van de AI afgewezen: {', '.join(parts)}."


def validate_ai_looks(
    proposals: list,
    items_by_id: dict[int, Item],
    rejected_pairs: set[frozenset[int]],
    existing: set[frozenset[int]],
    taken_names: set[str],
) -> LookReview:
    """Laat alleen door wat de kast zelf toestaat.

    Dit is het punt waar een voorstel een look wordt, en het staat met opzet
    hier in plaats van in :mod:`app.ai`: of twee kledingstukken samen mogen is
    een besluit van de bewoners, en dat besluit hoort niet afhankelijk te zijn
    van wat een model ervan vindt. Een outfit met een afgekeurd paar erin wordt
    daarom in z'n geheel geweigerd — er één stuk uit halen zou van hun "nee"
    een "ja, maar" maken.

    ``existing`` en ``taken_names`` groeien mee, zodat twee voorstellen in
    dezelfde ronde elkaar niet kunnen dubbelen.
    """
    review = LookReview()

    for proposal in proposals:
        items = [items_by_id[i] for i in proposal.item_ids if i in items_by_id]
        if len(items) < 2:
            review.too_small += 1
            continue

        ids = [item.id for item in items]
        blocked = any(
            frozenset((a, b)) in rejected_pairs
            for index, a in enumerate(ids)
            for b in ids[index + 1:]
        )
        if blocked:
            review.rejected_pair += 1
            continue

        key = frozenset(ids)
        if key in existing:
            review.already_existed += 1
            continue

        name = (proposal.name or "").strip()
        if not name or name.lower() in taken_names:
            # Geen bruikbare naam gekregen: de app verzint er zelf een, zodat
            # het voorstel niet om zoiets kleins sneuvelt.
            name = _name_for(items, taken_names)
        else:
            taken_names.add(name.lower())
        existing.add(key)

        review.accepted.append(
            LookPlan(
                name=name,
                items=items,
                # De tags van het model zijn een voorstel; wat de kleding zelf
                # zegt is een feit. Dus: alleen houden wat beide vinden.
                seasons=_shared(items, "season"),
                occasions=_agreed(items, "occasion", proposal.occasions),
                weather=_agreed(items, "weather", proposal.weather),
                styles=_union(items, "style"),
                reason=proposal.reason or "samengesteld met AI",
            )
        )
    return review


def _agreed(items: list[Item], attribute: str, proposed: list[str]) -> list[str]:
    """De tags die het model voorstelt *en* die de kleding niet tegenspreekt.

    Zegt geen enkel kledingstuk iets over dit veld, dan mag het voorstel staan:
    dat is precies het geval waarvoor de AI-laag bestaat. Zodra er wél iets
    getagd is, wint de doorsnede van de kleding — een look hoort niets te
    claimen wat z'n kleren tegenspreken.
    """
    shared = _shared(items, attribute)
    if not proposed:
        return shared
    if not shared:
        tagged = [item for item in items if split_tags(getattr(item, attribute))]
        return proposed if not tagged else []
    keep = {tag.lower() for tag in shared}
    return [tag for tag in proposed if tag.lower() in keep]
