"""Wat een AI-verzoek ongeveer kost, in centen.

Anthropic rekent per token en zegt in het antwoord hoeveel het er waren; wat
het antwoord *niet* zegt is wat dat kost. Daarvoor is een prijslijst nodig, en
die staat hier — op één plek, met de datum erbij, zodat duidelijk is dat het
een momentopname is en geen wet.

Twee dingen om in gedachten te houden bij alles wat deze module oplevert:

* **Het is een indicatie.** De officiële rekening staat bij Anthropic, niet
  hier. Een prijswijziging of een model dat deze tabel niet kent, laat het
  getal afwijken — daarom geeft :func:`cost_millicents` ``None`` terug voor een
  onbekend model in plaats van iets te verzinnen, en zegt het scherm erbij dat
  het een schatting is.
* **Het is klein.** Een kast van tweehonderd stuks laten taggen is één verzoek
  van een paar duizend tokens. In centen is dat vaak minder dan één, dus wordt
  er in duizendsten van een cent gerekend en pas bij het tonen afgerond.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Wanneer deze tarieven zijn overgenomen van de prijzenpagina. Staat in het
#: scherm, zodat niemand een bedrag van vorig jaar voor vandaag aanziet.
PRICES_AS_OF = "2026-05"

#: https://platform.claude.com/docs/en/about-claude/pricing


@dataclass(frozen=True)
class ModelPrice:
    """Dollar per miljoen tokens, zoals de prijzenpagina ze noemt."""

    input: float
    output: float

    @property
    def cache_read(self) -> float:
        """Een cache-treffer kost een tiende van een gewone invoertoken."""
        return self.input * 0.1

    @property
    def cache_write(self) -> float:
        """Iets in de cache zetten kost een kwart extra."""
        return self.input * 1.25


#: De modellen die :mod:`app.routers.ai_admin` aanbiedt, plus de varianten met
#: een datumsuffix die een operator via de omgeving kan meegeven. De opzoeking
#: is op prefix (zie :func:`price_for`), dus "claude-sonnet-5-20260514" vindt
#: gewoon de rij van "claude-sonnet-5".
PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(input=5.0, output=25.0),
    "claude-sonnet-5": ModelPrice(input=3.0, output=15.0),
    "claude-haiku-4-5": ModelPrice(input=1.0, output=5.0),
}


def price_for(model: str) -> ModelPrice | None:
    """De tarieven voor dit model, of ``None`` als we ze niet kennen.

    Op prefix, omdat een modelnaam een datumsuffix mag dragen en een operator
    die in de omgeving kan zetten. Langste prefix eerst, zodat een naam die
    bij twee rijen past bij de specifiekste hoort.
    """
    name = (model or "").strip().lower()
    if not name:
        return None
    for key in sorted(PRICES, key=len, reverse=True):
        if name.startswith(key):
            return PRICES[key]
    return None


def cost_millicents(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> int | None:
    """Wat dit verzoek ongeveer kostte, in duizendsten van een dollarcent.

    ``None`` voor een model dat niet in :data:`PRICES` staat: een verzonnen
    bedrag is erger dan geen bedrag, want het telt wél op in het totaal.
    """
    price = price_for(model)
    if price is None:
        return None
    dollars = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + cache_write_tokens * price.cache_write
    ) / 1_000_000
    return round(dollars * 100_000)
