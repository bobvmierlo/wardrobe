import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import AppFooter from "../components/AppFooter";
import LookMosaic from "../components/LookMosaic";
import Modal from "../components/Modal";
import OutfitStrip from "../components/OutfitStrip";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { weatherIcon } from "../components/WeatherCard";
import { useWardrobe } from "../wardrobe";
import type { Outfit, Week as WeekData } from "../types";

const DAY_NAMES = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"];

function shift(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function dayLabel(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return `${DAY_NAMES[(d.getDay() + 6) % 7]} ${d.getDate()}/${d.getMonth() + 1}`;
}

/** The week planner: one outfit per day, with the forecast beside it.
 *
 * Personal, even in a shared kast — see app/routers/planner.py. */
export default function Week() {
  const { current } = useWardrobe();
  const currentId = current?.id;

  const [start, setStart] = useState<string | undefined>(undefined);
  const [week, setWeek] = useState<WeekData | null>(null);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    if (!currentId) return;
    setLoading(true);
    try {
      const [data, list] = await Promise.all([
        api.week(currentId, start),
        api.listOutfits(currentId),
      ]);
      setWeek(data);
      setOutfits(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ophalen mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId, start]);

  useEffect(() => {
    load();
  }, [load]);

  async function plan(day: string, outfitId: number | null) {
    if (!currentId) return;
    try {
      await api.planDay(currentId, day, outfitId);
      setPicking(null);
      setQ("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  const today = new Date().toISOString().slice(0, 10);
  const pickingDay = picking ? week?.days.find((d) => d.day === picking) : undefined;
  const needle = q.trim().toLowerCase();
  const choices = needle
    ? outfits.filter((o) =>
        [o.name, ...o.occasions, ...o.style_tags, ...o.items.map((i) => i.name)]
          .join(" ")
          .toLowerCase()
          .includes(needle),
      )
    : outfits;

  return (
    <>
      <div className="topbar">
        <h1>Weekplanner</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}

        <div className="row spread" style={{ marginBottom: 12 }}>
          <button className="btn-ghost" onClick={() => setStart(shift(week?.start ?? today, -7))}>
            ← Vorige
          </button>
          <span className="muted" style={{ fontSize: "0.85rem" }}>
            {week ? `week van ${dayLabel(week.start)}` : ""}
          </span>
          <button className="btn-ghost" onClick={() => setStart(shift(week?.start ?? today, 7))}>
            Volgende →
          </button>
        </div>
        {week && week.start !== undefined && start !== undefined && (
          <button className="btn-ghost btn-block" onClick={() => setStart(undefined)}>
            Naar deze week
          </button>
        )}

        {loading && <div className="spinner" />}

        <div className="week-grid" style={{ marginTop: 12 }}>
          {week?.days.map((day) => (
            <div className={`card day-card ${day.day === today ? "today" : ""}`} key={day.day}>
              <div className="day-head">
                <span className="day-name">{dayLabel(day.day)}</span>
                {day.weather && (
                  <span className="day-weather">
                    {weatherIcon(day.weather.tags)}{" "}
                    {day.weather.high !== null ? `${Math.round(day.weather.high)}°` : ""}
                    {day.weather.precipitation_chance !== null
                      ? ` · ${day.weather.precipitation_chance}%`
                      : ""}
                  </span>
                )}
              </div>

              {day.outfit ? (
                <>
                  <strong style={{ fontSize: "0.9rem" }}>{day.outfit.name}</strong>
                  <OutfitStrip items={day.outfit.items} size={56} />
                  <div className="row" style={{ gap: 8 }}>
                    <button className="btn-ghost" onClick={() => setPicking(day.day)}>
                      Andere look
                    </button>
                    <button className="btn-ghost" onClick={() => plan(day.day, null)}>
                      Leegmaken
                    </button>
                  </div>
                </>
              ) : (
                <button className="btn-ghost" onClick={() => setPicking(day.day)}>
                  + Look kiezen
                </button>
              )}
            </div>
          ))}
        </div>

        <AppFooter />
      </div>

      {/* Choosing what to wear on Tuesday by reading a list of names is not
          choosing: you pick a look because of what it looks like. So the
          picker shows the looks, in a dialog that opens where you are rather
          than inside the day card you happened to tap. */}
      {picking && (
        <Modal
          wide
          title={`Look kiezen voor ${dayLabel(picking)}`}
          onClose={() => {
            setPicking(null);
            setQ("");
          }}
        >
          {outfits.length === 0 ? (
            <p className="muted">
              Nog geen looks om te plannen. Maak er eerst een bij <strong>Looks</strong>.
            </p>
          ) : (
            <>
              <div className="filterbar">
                <input
                  className="search"
                  placeholder="Zoek een look…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              {choices.length === 0 && <p className="muted">Geen look gevonden.</p>}
              <div className="look-pick-grid">
                {choices.map((outfit) => {
                  // The whole point of the forecast column: say out loud when
                  // a look is tagged for other weather than the day.
                  const mismatch =
                    pickingDay?.weather &&
                    outfit.weather_tags.length > 0 &&
                    !outfit.weather_tags.some((t) => pickingDay.weather!.tags.includes(t));
                  return (
                    <button
                      type="button"
                      className="look-pick-card"
                      key={outfit.id}
                      onClick={() => plan(picking, outfit.id)}
                    >
                      <LookMosaic items={outfit.items} max={4} compact />
                      <span className="look-pick-name">{outfit.name}</span>
                      {mismatch ? (
                        <span className="look-pick-note warn">Past niet bij dit weer</span>
                      ) : (
                        outfit.occasions.length > 0 && (
                          <span className="look-pick-note">{outfit.occasions.join(" · ")}</span>
                        )
                      )}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
