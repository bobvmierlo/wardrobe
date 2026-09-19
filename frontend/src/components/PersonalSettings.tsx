import { useState } from "react";
import { api } from "../api";
import { useTheme } from "../theme";
import { THEMES, WEATHER_TAGS, type Place } from "../types";

/** The settings that belong to one person: their palette, where the forecast
 *  comes from, and whether a wear log is kept for them at all. */
export default function PersonalSettings() {
  const { theme, preferences, setTheme, save } = useTheme();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const found = await api.searchPlaces(query.trim());
      setResults(found);
      if (found.length === 0) setError("Niets gevonden. Probeer een plaatsnaam of een postcode.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Zoeken mislukt");
    } finally {
      setBusy(false);
    }
  }

  async function choose(place: Place) {
    setBusy(true);
    try {
      await save({
        location_label: place.label,
        latitude: place.latitude,
        longitude: place.longitude,
        weather_mode: "auto",
      });
      setResults(null);
      setQuery("");
      setNote(`Weer wordt nu opgehaald voor ${place.label}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    } finally {
      setBusy(false);
    }
  }

  /** Ask the browser where we are. Needs an explicit click: the permission
   *  prompt belongs to a gesture, and nobody should be asked out of nowhere. */
  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("Deze browser kan je locatie niet doorgeven. Zoek anders op plaatsnaam.");
      return;
    }
    setBusy(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        try {
          // The browser hands us two numbers; the server turns them into a
          // name so the screen does not have to show "52.09, 5.12".
          const place = await api.lookupPlace(latitude, longitude);
          await choose({ ...place, latitude, longitude });
        } catch {
          await save({
            location_label: `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`,
            latitude,
            longitude,
            weather_mode: "auto",
          });
          setNote("Locatie opgeslagen.");
        } finally {
          setBusy(false);
        }
      },
      (err) => {
        setBusy(false);
        setError(
          err.code === err.PERMISSION_DENIED
            ? "Geen toestemming gegeven. Je kunt hieronder ook op plaatsnaam of postcode zoeken."
            : "Je locatie kon niet worden bepaald. Zoek anders op plaatsnaam.",
        );
      },
      { timeout: 10000, maximumAge: 600000 },
    );
  }

  async function clearLocation() {
    await save({ location_label: "" });
    setNote("Locatie gewist.");
  }

  async function toggleManualTag(tag: string) {
    const cur = preferences?.manual_weather ?? [];
    const next = cur.includes(tag) ? cur.filter((t) => t !== tag) : [...cur, tag];
    await save({ manual_weather: next, weather_mode: "manual" });
  }

  return (
    <>
      <div className="card" id="thema" style={{ padding: 16, scrollMarginTop: 80 }}>
        <h3 style={{ marginTop: 0 }}>Kleurstelling</h3>
        <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
          Geldt alleen voor jou — deel je een kast, dan houdt de ander gewoon zijn eigen kleuren.
        </p>
        <div className="theme-grid">
          {THEMES.map((option) => (
            <button
              type="button"
              key={option.id}
              className={`theme-card ${theme === option.id ? "active" : ""}`}
              aria-pressed={theme === option.id}
              onClick={() => setTheme(option.id)}
            >
              <span className="theme-swatch" aria-hidden="true">
                {option.swatch.map((color) => (
                  <span key={color} style={{ background: color }} />
                ))}
              </span>
              <span style={{ fontWeight: 600 }}>{option.label}</span>
              <div className="muted" style={{ fontSize: "0.78rem" }}>
                {option.hint}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="card" id="weer" style={{ padding: 16, scrollMarginTop: 80 }}>
        <h3 style={{ marginTop: 0 }}>Weer en locatie</h3>
        {!preferences?.weather_available ? (
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            De beheerder heeft het ophalen van het weer uitgezet in deze installatie. Je kunt het
            weer hieronder wel handmatig instellen.
          </p>
        ) : (
          <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
            De app haalt de echte weersverwachting op voor jouw plek, via de server — je browser
            praat dus niet rechtstreeks met een weerdienst. Geen account of sleutel nodig.
          </p>
        )}

        {error && <div className="error">{error}</div>}
        {note && <div className="notice">{note}</div>}

        <div className="row" style={{ gap: 10, marginBottom: 10 }}>
          <strong style={{ flex: 1 }}>
            {preferences?.location_label ?? "Nog geen locatie gekozen"}
          </strong>
          {preferences?.location_label && (
            <button className="btn-ghost" onClick={clearLocation} disabled={busy}>
              Wissen
            </button>
          )}
        </div>

        <button className="btn-ghost btn-block" onClick={useMyLocation} disabled={busy}>
          📍 Gebruik mijn huidige locatie
        </button>

        <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <input
            value={query}
            placeholder="Plaatsnaam of postcode…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                search();
              }
            }}
          />
          <button className="btn-ghost" onClick={search} disabled={busy || !query.trim()}>
            Zoeken
          </button>
        </div>

        {results && results.length > 0 && (
          <div className="stack" style={{ marginTop: 10 }}>
            {results.map((place) => (
              <button
                className="btn-ghost"
                key={`${place.latitude},${place.longitude},${place.label}`}
                style={{ textAlign: "left" }}
                onClick={() => choose(place)}
              >
                {place.label}
                {place.postcode ? ` · ${place.postcode}` : ""}
              </button>
            ))}
          </div>
        )}

        <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />

        <h4 style={{ margin: "0 0 6px" }}>Liever zelf invullen</h4>
        <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
          Geen zin in een locatie? Kies zelf wat voor weer het is. De aanbevelingen werken er net zo
          goed op — alleen de temperatuur weet de app dan niet.
        </p>
        <div className="chips wrap">
          {WEATHER_TAGS.map((tag) => (
            <button
              type="button"
              key={tag}
              className={`chip ${
                preferences?.weather_mode === "manual" && preferences.manual_weather.includes(tag)
                  ? "active"
                  : ""
              }`}
              onClick={() => toggleManualTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
        {preferences?.weather_mode === "manual" && preferences.latitude !== null && (
          <button
            className="btn-ghost btn-block"
            style={{ marginTop: 10 }}
            onClick={() => save({ weather_mode: "auto" })}
          >
            Terug naar de echte weersverwachting
          </button>
        )}
      </div>

      <div className="card" id="draaglogboek" style={{ padding: 16, scrollMarginTop: 80 }}>
        <h3 style={{ marginTop: 0 }}>Draaglogboek</h3>
        <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
          Houd bij wat je wanneer droeg. Dat zorgt ervoor dat de app niet drie dagen achter elkaar
          dezelfde look voorstelt, en laat zien wat je eigenlijk nooit aantrekt. Staat standaard uit
          — niet iedereen wil dit — en is alleen van jou: niemand anders ziet het, ook niet in een
          gedeelde kast.
        </p>
        <label className="row" style={{ gap: 10, cursor: "pointer" }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={preferences?.wear_log_enabled ?? false}
            onChange={(e) => save({ wear_log_enabled: e.target.checked })}
          />
          <span>Draaglogboek bijhouden</span>
        </label>
      </div>
    </>
  );
}
