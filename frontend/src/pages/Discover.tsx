import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import AppFooter from "../components/AppFooter";
import OutfitStrip from "../components/OutfitStrip";
import TagPicker from "../components/TagPicker";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import { SEASONS, WEATHER_TAGS, type Occasion, type OutfitSuggestion } from "../types";

/** "Ontdekken": build outfits to order.
 *
 * Unlike "Vandaag" this ignores the forecast and your wear log — it is for
 * browsing what the kast *could* do, not for deciding what to put on now. */
export default function Discover() {
  const { current, canEdit } = useWardrobe();
  const currentId = current?.id;

  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [occasion, setOccasion] = useState("");
  const [season, setSeason] = useState("");
  const [weather, setWeather] = useState<string[]>([]);
  const [results, setResults] = useState<OutfitSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<number[]>([]);

  useEffect(() => {
    api.listOccasions().then(setOccasions).catch(() => setOccasions([]));
  }, []);

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
          weather: weather.length ? weather : undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Zoeken mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId, occasion, season, weather]);

  useEffect(() => {
    search();
  }, [search]);

  async function keep(suggestion: OutfitSuggestion, index: number) {
    if (!currentId) return;
    try {
      await api.createOutfit(currentId, {
        name: `${occasion || season || "Look"} ${new Date().toLocaleDateString("nl-NL")}`,
        item_ids: suggestion.items.map((i) => i.id),
        occasions: occasion ? [occasion] : [],
        seasons: season ? [season] : [],
        weather_tags: weather,
      });
      setSaved((cur) => [...cur, index]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  return (
    <>
      <div className="topbar">
        <h1>Ontdekken</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}
        <p className="muted" style={{ marginTop: 0, fontSize: "0.9rem" }}>
          Kies waar je heen gaat, in welk seizoen en bij welk weer — de app stelt combinaties voor
          uit je eigen kast.
        </p>

        <div className="field">
          <label>Gelegenheid</label>
          <div className="chips wrap">
            <button
              type="button"
              className={`chip ${occasion === "" ? "active" : ""}`}
              onClick={() => setOccasion("")}
            >
              Maakt niet uit
            </button>
            {occasions.map((o) => (
              <button
                type="button"
                key={o.id}
                className={`chip ${occasion === o.name ? "active" : ""}`}
                onClick={() => setOccasion(o.name)}
              >
                {o.name}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label>Seizoen</label>
          <div className="chips wrap">
            <button
              type="button"
              className={`chip ${season === "" ? "active" : ""}`}
              onClick={() => setSeason("")}
            >
              Maakt niet uit
            </button>
            {SEASONS.filter((s) => s !== "Alle seizoenen").map((s) => (
              <button
                type="button"
                key={s}
                className={`chip ${season === s ? "active" : ""}`}
                onClick={() => setSeason(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <TagPicker label="Weer" options={WEATHER_TAGS} value={weather} onChange={setWeather} />

        <button className="btn-primary btn-block" onClick={search} disabled={loading}>
          {loading ? "Bezig…" : "Stel iets voor"}
        </button>

        {!loading && results.length === 0 && (
          <div className="empty">
            <div className="big">🧭</div>
            <p>
              Niets gevonden met deze filters. Probeer er een los te laten, of tag meer
              kledingstukken voor deze gelegenheid.
            </p>
          </div>
        )}

        {results.map((suggestion, index) => (
          <div className="card rec-card" key={index}>
            <OutfitStrip items={suggestion.items} />
            <p className="rec-reason">{suggestion.reason}</p>
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
