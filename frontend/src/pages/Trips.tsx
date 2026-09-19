import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import AppFooter from "../components/AppFooter";
import OutfitStrip from "../components/OutfitStrip";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useConfirm } from "../confirm";
import { useWardrobe } from "../wardrobe";
import type { Outfit, Trip, TripDetail } from "../types";

/** "Reistas": which looks are coming along, and the packing list they imply.
 *
 * The list is derived from the looks rather than stored, so editing a look
 * can never leave a trip listing something it no longer needs. */
export default function Trips() {
  const { current, canEdit } = useWardrobe();
  const confirm = useConfirm();
  const currentId = current?.id;

  const [trips, setTrips] = useState<Trip[]>([]);
  const [open, setOpen] = useState<TripDetail | null>(null);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", destination: "", starts_on: "", ends_on: "" });

  const load = useCallback(async () => {
    if (!currentId) return;
    setLoading(true);
    try {
      const [list, looks] = await Promise.all([
        api.listTrips(currentId),
        api.listOutfits(currentId),
      ]);
      setTrips(list);
      setOutfits(looks);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ophalen mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!currentId || !form.name.trim()) return;
    try {
      const trip = await api.createTrip(currentId, {
        name: form.name.trim(),
        destination: form.destination.trim() || null,
        starts_on: form.starts_on || null,
        ends_on: form.ends_on || null,
      });
      setCreating(false);
      setForm({ name: "", destination: "", starts_on: "", ends_on: "" });
      setOpen(trip);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  async function remove(trip: Trip) {
    const ok = await confirm({
      title: `"${trip.name}" verwijderen?`,
      body: "De reis en het afvinken verdwijnen. Je looks en kleding blijven.",
      confirmLabel: "Verwijderen",
    });
    if (!ok) return;
    await api.deleteTrip(trip.id);
    setOpen(null);
    load();
  }

  if (open) {
    const progress = open.item_count ? Math.round((open.packed_count / open.item_count) * 100) : 0;
    return (
      <>
        <div className="topbar">
          <h1>{open.name}</h1>
          <button className="btn-ghost" onClick={() => setOpen(null)}>
            ← Terug
          </button>
        </div>
        <div className="content">
          {error && <div className="error">{error}</div>}
          <p className="muted" style={{ marginTop: 0 }}>
            {[open.destination, open.starts_on, open.ends_on].filter(Boolean).join(" · ") || "Geen datums"}
          </p>

          <div className="card" style={{ padding: 14 }}>
            <div className="row spread">
              <strong>Paklijst</strong>
              <span className="muted">
                {open.packed_count}/{open.item_count} ingepakt
              </span>
            </div>
            <div className="bar-track" style={{ marginTop: 8 }}>
              <span className="bar-fill" style={{ width: `${progress}%` }} />
            </div>
            <div style={{ marginTop: 10 }}>
              {open.packing.length === 0 && (
                <p className="muted">Kies hieronder welke looks meegaan — de paklijst volgt vanzelf.</p>
              )}
              {open.packing.map((entry) => (
                <label className={`pack-row ${entry.packed ? "done" : ""}`} key={entry.item.id}>
                  <input
                    type="checkbox"
                    style={{ width: "auto" }}
                    checked={entry.packed}
                    onChange={async (e) => setOpen(await api.setPacked(open.id, entry.item.id, e.target.checked))}
                  />
                  <span className="pack-name">{entry.item.name}</span>
                  {entry.used_in > 1 && <span className="muted">{entry.used_in} looks</span>}
                </label>
              ))}
            </div>
          </div>

          <h2>Looks die meegaan</h2>
          {open.outfits.map((outfit) => (
            <div className="card rec-card" key={outfit.id}>
              <div className="rec-head">
                <span className="rec-title">{outfit.name}</span>
                {canEdit && (
                  <button
                    className="btn-ghost"
                    onClick={async () => setOpen(await api.removeTripOutfit(open.id, outfit.id))}
                  >
                    Laat thuis
                  </button>
                )}
              </div>
              <OutfitStrip items={outfit.items} size={56} />
            </div>
          ))}

          {canEdit && (
            <>
              <h2>Nog toevoegen</h2>
              <div className="stack">
                {outfits
                  .filter((o) => !open.outfits.some((x) => x.id === o.id))
                  .map((outfit) => (
                    <button
                      className="btn-ghost"
                      key={outfit.id}
                      style={{ textAlign: "left" }}
                      onClick={async () => setOpen(await api.addTripOutfit(open.id, outfit.id))}
                    >
                      + {outfit.name}
                    </button>
                  ))}
                {outfits.length === 0 && (
                  <p className="muted">Maak eerst een paar looks; daar komt de paklijst uit.</p>
                )}
              </div>
            </>
          )}

          <AppFooter />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="topbar">
        <h1>Reistas</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}
        {canEdit && !creating && (
          <button className="btn-primary btn-block" onClick={() => setCreating(true)}>
            + Nieuwe reis
          </button>
        )}

        {creating && (
          <div className="card" style={{ padding: 16 }}>
            <div className="field">
              <label>Naam *</label>
              <input
                value={form.name}
                placeholder="Weekend Parijs"
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Bestemming</label>
              <input
                value={form.destination}
                onChange={(e) => setForm({ ...form, destination: e.target.value })}
              />
            </div>
            <div className="row" style={{ gap: 10 }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Van</label>
                <input
                  type="date"
                  value={form.starts_on}
                  onChange={(e) => setForm({ ...form, starts_on: e.target.value })}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Tot</label>
                <input
                  type="date"
                  value={form.ends_on}
                  onChange={(e) => setForm({ ...form, ends_on: e.target.value })}
                />
              </div>
            </div>
            <div className="row" style={{ gap: 10 }}>
              <button className="btn-ghost" style={{ flex: 1 }} onClick={() => setCreating(false)}>
                Annuleren
              </button>
              <button className="btn-primary" style={{ flex: 1 }} onClick={create}>
                Aanmaken
              </button>
            </div>
          </div>
        )}

        {loading && <div className="spinner" />}
        {!loading && trips.length === 0 && (
          <div className="empty">
            <div className="big">🧳</div>
            <p>Nog geen reizen. Maak er een aan en kies welke looks meegaan.</p>
          </div>
        )}

        {trips.map((trip) => (
          <div className="card rec-card" key={trip.id}>
            <div className="rec-head">
              <span className="rec-title">{trip.name}</span>
              <span className="rec-source">
                {trip.packed_count}/{trip.item_count} ingepakt
              </span>
            </div>
            <p className="rec-reason">
              {[trip.destination, trip.starts_on, trip.ends_on].filter(Boolean).join(" · ") ||
                "Geen datums"}{" "}
              · {trip.outfit_count} look(s)
            </p>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn-ghost" onClick={async () => setOpen(await api.getTrip(trip.id))}>
                Openen
              </button>
              {canEdit && (
                <button className="btn-danger" onClick={() => remove(trip)}>
                  Verwijderen
                </button>
              )}
            </div>
          </div>
        ))}

        <AppFooter />
      </div>
    </>
  );
}
