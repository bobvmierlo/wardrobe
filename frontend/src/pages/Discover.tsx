import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import AppFooter from "../components/AppFooter";
import FilterBar from "../components/FilterBar";
import LookMosaic from "../components/LookMosaic";
import OutfitStrip from "../components/OutfitStrip";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import {
  SEASONS,
  WEATHER_TAGS,
  type Item,
  type Occasion,
  type Outfit,
  type OutfitSuggestion,
  type Reading,
} from "../types";

/** "Ontdekken": build outfits to order.
 *
 * Unlike "Vandaag" this ignores the forecast and your wear log — it is for
 * browsing what the kast *could* do, not for deciding what to put on now.
 *
 * Two ways in, because people arrive with two different questions. "Zaterdag
 * naar een festival" is a sentence, not three dropdowns, so there is a box to
 * type it in; and "ik wil dit vandaag aan" is not a search at all, so there is
 * a garment to build around. Both end up in the same machinery.
 */
export default function Discover() {
  const { current, canEdit } = useWardrobe();
  const currentId = current?.id;

  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [occasion, setOccasion] = useState("");
  const [season, setSeason] = useState("");
  const [weather, setWeather] = useState("");
  const [around, setAround] = useState("");
  const [results, setResults] = useState<OutfitSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<number[]>([]);

  // The typed sentence, and what the server made of it.
  const [sentence, setSentence] = useState("");
  const [reading, setReading] = useState<Reading | null>(null);
  const [matches, setMatches] = useState<Outfit[]>([]);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    api.listOccasions().then(setOccasions).catch(() => setOccasions([]));
  }, []);

  useEffect(() => {
    if (!currentId) return;
    api.listItems(currentId).then(setItems).catch(() => setItems([]));
  }, [currentId]);

  const search = useCallback(async () => {
    if (!currentId) return;
    setLoading(true);
    setError(null);
    setSaved([]);
    try {
      setResults(
        await api.discover(currentId, {
          occasion: occasion || undefined,
          season: season || undefined,
          weather: weather ? [weather] : undefined,
          around: around ? Number(around) : undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Zoeken mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId, occasion, season, weather, around]);

  useEffect(() => {
    search();
  }, [search]);

  /** Read the sentence, then put what it said into the dropdowns.
   *
   * Deliberately not a separate mode: the filters end up showing what was
   * understood, so the answer is correctable with one tap instead of by
   * rephrasing a sentence and hoping. */
  async function describe() {
    if (!currentId || !sentence.trim()) return;
    setAsking(true);
    setError(null);
    try {
      const answer = await api.describe(currentId, sentence.trim());
      setReading(answer.reading);
      setMatches(answer.saved);
      setOccasion(answer.reading?.occasion ?? "");
      setSeason(answer.reading?.season ?? "");
      setWeather(answer.reading?.weather[0] ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Zoeken mislukt");
    } finally {
      setAsking(false);
    }
  }

  async function keep(suggestion: OutfitSuggestion, index: number) {
    if (!currentId) return;
    try {
      await api.createOutfit(currentId, {
        name: `${occasion || season || "Look"} ${new Date().toLocaleDateString("nl-NL")}`,
        item_ids: suggestion.items.map((i) => i.id),
        occasions: occasion ? [occasion] : [],
        seasons: season ? [season] : [],
        weather_tags: weather ? [weather] : [],
      });
      setSaved((cur) => [...cur, index]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  const anchor = useMemo(
    () => items.find((i) => String(i.id) === around) ?? null,
    [items, around],
  );

  function clearAll() {
    setOccasion("");
    setSeason("");
    setWeather("");
    setAround("");
    setSentence("");
    setReading(null);
    setMatches([]);
  }

  const filtering = occasion !== "" || season !== "" || weather !== "" || around !== "";

  return (
    <>
      <div className="topbar">
        <h1>Ontdekken</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}

        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>Beschrijf wat je gaat doen</h3>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
            Bijv. "Zaterdag met vriendinnen naar een wijnfestival buiten in Gemert" — de app zet
            dat om in gelegenheid, seizoen en weer, en zoekt daar looks bij. Dat gebeurt op de
            server zelf, zonder AI en zonder dat er iets de deur uit gaat.
          </p>
          <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
            <textarea
              value={sentence}
              placeholder="Beschrijf de gelegenheid…"
              style={{ minHeight: 60 }}
              onChange={(e) => setSentence(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  describe();
                }
              }}
            />
            <button
              className="btn-primary"
              style={{ flex: "none" }}
              disabled={asking || !sentence.trim()}
              onClick={describe}
            >
              {asking ? "Bezig…" : "Vind looks"}
            </button>
          </div>

          {/* What it understood, always — an empty list because it read
              nothing is a different problem from an empty kast. */}
          {reading && (
            <div className="notice" style={{ marginTop: 12 }}>
              {reading.understood ? (
                <>
                  Gelezen als:{" "}
                  <strong>
                    {[reading.occasion, reading.season, ...reading.weather]
                      .filter(Boolean)
                      .join(" · ")}
                  </strong>
                  {reading.matched.length > 0 && (
                    <span className="muted"> (op "{reading.matched.join('", "')}")</span>
                  )}
                  . Staat hieronder ingevuld — pas het gerust aan.
                </>
              ) : (
                <>
                  Hier kon de app geen gelegenheid, seizoen of weer uit halen. Kies het hieronder
                  zelf, dan weet 'ie het wel.
                </>
              )}
            </div>
          )}
        </div>

        <FilterBar active={filtering ? 1 : 0}>
          <select
            className={occasion ? "on" : ""}
            aria-label="Gelegenheid"
            value={occasion}
            onChange={(e) => setOccasion(e.target.value)}
          >
            <option value="">Gelegenheid maakt niet uit</option>
            {occasions.map((o) => (
              <option key={o.id} value={o.name}>
                {o.name}
              </option>
            ))}
          </select>
          <select
            className={season ? "on" : ""}
            aria-label="Seizoen"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
          >
            <option value="">Seizoen maakt niet uit</option>
            {SEASONS.filter((s) => s !== "Alle seizoenen").map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className={weather ? "on" : ""}
            aria-label="Weer"
            value={weather}
            onChange={(e) => setWeather(e.target.value)}
          >
            <option value="">Weer maakt niet uit</option>
            {WEATHER_TAGS.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
          <select
            className={around ? "on" : ""}
            aria-label="Bouw rond een kledingstuk"
            value={around}
            onChange={(e) => setAround(e.target.value)}
          >
            <option value="">Verras me — geen basisstuk</option>
            {items.map((i) => (
              <option key={i.id} value={String(i.id)}>
                {i.name} ({i.category})
              </option>
            ))}
          </select>
        </FilterBar>

        {filtering && (
          <div className="filter-summary">
            <span>
              {anchor ? `Alles met "${anchor.name}" erin` : "Voorstellen uit je eigen kast"}
            </span>
            <button className="btn-ghost" onClick={clearAll}>
              Filters wissen
            </button>
          </div>
        )}

        {/* Looks you already saved come first and stay separate. A look is a
            decision somebody took; a suggestion is one the app just thought up
            and that does not exist until you keep it. */}
        {matches.length > 0 && (
          <>
            <h2>Looks die je al hebt</h2>
            <div className="looks-grid">
              {matches.map((outfit) => (
                <Link
                  className="card look-card"
                  to={`/looks?outfit=${outfit.id}`}
                  key={outfit.id}
                  style={{ color: "var(--text)" }}
                >
                  <LookMosaic items={outfit.items} />
                  <div>
                    <div className="look-title">{outfit.name}</div>
                    <div className="look-sub">
                      {[...outfit.occasions, ...outfit.weather_tags].join(" · ")}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </>
        )}

        <h2>{matches.length > 0 ? "En dit kun je nog meer maken" : "Voorstellen"}</h2>

        {loading && <div className="spinner" />}

        {!loading && results.length === 0 && (
          <div className="empty">
            <div className="big">🧭</div>
            <p>
              {anchor
                ? `Niets gevonden om "${anchor.name}" heen. Probeer een filter los te laten, of kies een ander basisstuk.`
                : "Niets gevonden met deze filters. Probeer er een los te laten, of tag meer kledingstukken voor deze gelegenheid."}
            </p>
          </div>
        )}

        {results.map((suggestion, index) => (
          <div className="card rec-card" key={index} style={{ marginBottom: 12 }}>
            <OutfitStrip items={suggestion.items} />
            <p className="rec-reason" style={{ margin: 0 }}>
              {suggestion.reason}
            </p>
            {canEdit && (
              <button
                className="btn-ghost"
                disabled={saved.includes(index)}
                onClick={() => keep(suggestion, index)}
              >
                {saved.includes(index) ? "✓ Bewaard als look" : "Bewaar als look"}
              </button>
            )}
          </div>
        ))}

        <AppFooter />
      </div>
    </>
  );
}
