import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import AppFooter from "../components/AppFooter";
import OutfitStrip from "../components/OutfitStrip";
import WeatherCard from "../components/WeatherCard";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useTheme } from "../theme";
import { useWardrobe } from "../wardrobe";
import type { Occasion, Recommendation, RecommendationPage } from "../types";

const TODAY = () => new Date().toISOString().slice(0, 10);

/** "Vandaag": what the weather is doing, and what you could put on because
 *  of it. The one screen that answers the question the app exists for. */
export default function Today() {
  const { current, canEdit } = useWardrobe();
  const { preferences, refresh: refreshPrefs } = useTheme();
  const currentId = current?.id;

  const [page, setPage] = useState<RecommendationPage | null>(null);
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [occasion, setOccasion] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<number[]>([]);
  const [wornToday, setWornToday] = useState<number[]>([]);

  useEffect(() => {
    api.listOccasions().then(setOccasions).catch(() => setOccasions([]));
  }, []);

  const load = useCallback(async () => {
    if (!currentId) return;
    setLoading(true);
    setError(null);
    try {
      setPage(await api.recommendations(currentId, occasion || undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ophalen mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId, occasion]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveAsOutfit(rec: Recommendation, index: number) {
    if (!currentId) return;
    try {
      const outfit = await api.createOutfit(currentId, {
        name: rec.outfit_name ?? `Voorstel van ${new Date().toLocaleDateString("nl-NL")}`,
        item_ids: rec.items.map((i) => i.id),
        // Tag it with what it was recommended *for*: that is what makes it
        // come back next time the weather looks like this.
        weather_tags: page?.weather?.tags ?? [],
        occasions: occasion ? [occasion] : [],
      });
      setSavedIds((cur) => [...cur, index]);
      return outfit;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  async function wearToday(outfitId: number) {
    try {
      await api.logWear(outfitId, TODAY());
      setWornToday((cur) => [...cur, outfitId]);
      // Wearing it changes what should be suggested next, so ask again.
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  const needsLocation =
    preferences !== null &&
    preferences.weather_mode === "auto" &&
    preferences.latitude === null;

  return (
    <>
      <div className="topbar">
        <h1>Vandaag</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}

        <WeatherCard
          weather={page?.weather ?? null}
          advice={page?.advice}
          empty={
            needsLocation ? (
              <div className="notice">
                Nog geen locatie ingesteld.{" "}
                <Link to="/settings#weer" onClick={() => refreshPrefs()}>
                  Kies een plaats
                </Link>{" "}
                — of stel het weer handmatig in — dan stemt de app je outfits erop af.
              </div>
            ) : (
              <div className="notice">
                Het weer is nog niet bekend. Kijk bij{" "}
                <Link to="/settings#weer">Instellingen → Weer</Link>.
              </div>
            )
          }
        />

        <div className="field" style={{ marginTop: 16 }}>
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

        {loading && <div className="spinner" />}

        {!loading && page?.empty_reason && (
          <div className="empty">
            <div className="big">🤔</div>
            <p>{page.empty_reason}</p>
            <Link className="cta-link btn-primary" to="/add">
              Kledingstuk toevoegen
            </Link>
          </div>
        )}

        {!loading &&
          page?.recommendations.map((rec, index) => (
            <div className="card rec-card" key={`${rec.outfit_id ?? "new"}-${index}`}>
              <div className="rec-head">
                <span className="rec-title">
                  {rec.outfit_name ?? "Zo zou je het kunnen doen"}
                </span>
                <span className="rec-source">
                  {rec.source === "saved" ? "opgeslagen outfit" : "voorstel"}
                </span>
              </div>
              <OutfitStrip items={rec.items} />
              <p className="rec-reason">{rec.reason}</p>
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                {rec.outfit_id !== null && preferences?.wear_log_enabled && (
                  <button
                    className="btn-ghost"
                    disabled={wornToday.includes(rec.outfit_id) || rec.last_worn === TODAY()}
                    onClick={() => wearToday(rec.outfit_id!)}
                  >
                    {wornToday.includes(rec.outfit_id) || rec.last_worn === TODAY()
                      ? "✓ Vandaag gedragen"
                      : "Dit trek ik aan"}
                  </button>
                )}
                {rec.source === "new" && canEdit && (
                  <button
                    className="btn-ghost"
                    disabled={savedIds.includes(index)}
                    onClick={() => saveAsOutfit(rec, index)}
                  >
                    {savedIds.includes(index) ? "✓ Opgeslagen" : "Bewaar als outfit"}
                  </button>
                )}
                {rec.outfit_id !== null && (
                  <Link className="btn-ghost" to={`/looks?outfit=${rec.outfit_id}`}>
                    Bekijken
                  </Link>
                )}
              </div>
            </div>
          ))}

        <AppFooter />
      </div>
    </>
  );
}
