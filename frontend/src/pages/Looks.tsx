import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import AutofillCard from "../components/AutofillCard";
import OutfitStrip from "../components/OutfitStrip";
import TagPicker from "../components/TagPicker";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useConfirm } from "../confirm";
import { useTheme } from "../theme";
import { useWardrobe } from "../wardrobe";
import { SEASONS, WEATHER_TAGS, type Item, type Occasion, type Outfit } from "../types";

const TODAY = () => new Date().toISOString().slice(0, 10);

interface Draft {
  id: number | null;
  name: string;
  itemIds: number[];
  notes: string;
  seasons: string[];
  occasions: string[];
  weather: string[];
  styles: string[];
}

function emptyDraft(): Draft {
  return {
    id: null,
    name: "",
    itemIds: [],
    notes: "",
    seasons: [],
    occasions: [],
    weather: [],
    styles: [],
  };
}

function draftOf(outfit: Outfit): Draft {
  return {
    id: outfit.id,
    name: outfit.name,
    itemIds: outfit.items.map((i) => i.id),
    notes: outfit.notes ?? "",
    seasons: outfit.seasons,
    occasions: outfit.occasions,
    weather: outfit.weather_tags,
    styles: outfit.style_tags,
  };
}

/** "Looks": the outfits somebody put together and saved, with the tags that
 *  say when to wear them. Distinct from /outfits, which shows what the swipe
 *  decided goes with what — see app/models.py:Outfit. */
export default function Looks() {
  const { current, canEdit } = useWardrobe();
  const { preferences } = useTheme();
  const confirm = useConfirm();
  const currentId = current?.id;
  const [params, setParams] = useSearchParams();

  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    if (!currentId) return;
    setLoading(true);
    try {
      const [list, kast] = await Promise.all([
        api.listOutfits(currentId),
        api.listItems(currentId),
      ]);
      setOutfits(list);
      setItems(kast);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ophalen mislukt");
    } finally {
      setLoading(false);
    }
  }, [currentId]);

  useEffect(() => {
    load();
    api.listOccasions().then(setOccasions).catch(() => setOccasions([]));
  }, [load]);

  // Opened from "Vandaag" with ?outfit=…: scroll that one into view.
  const highlight = Number(params.get("outfit")) || null;
  useEffect(() => {
    if (!highlight) return;
    document.getElementById(`outfit-${highlight}`)?.scrollIntoView({ block: "center" });
  }, [highlight, outfits]);

  const shown = useMemo(() => {
    if (!filter) return outfits;
    return outfits.filter((o) => o.occasions.includes(filter));
  }, [outfits, filter]);

  async function save() {
    if (!currentId || !draft) return;
    if (!draft.name.trim() || draft.itemIds.length === 0) {
      setError("Geef de look een naam en kies minstens één kledingstuk.");
      return;
    }
    setBusy(true);
    setError(null);
    const body = {
      name: draft.name.trim(),
      item_ids: draft.itemIds,
      notes: draft.notes,
      seasons: draft.seasons,
      occasions: draft.occasions,
      weather_tags: draft.weather,
      style_tags: draft.styles,
    };
    try {
      if (draft.id === null) await api.createOutfit(currentId, body);
      else await api.updateOutfit(draft.id, body);
      setDraft(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    } finally {
      setBusy(false);
    }
  }

  async function remove(outfit: Outfit) {
    const ok = await confirm({
      title: `"${outfit.name}" verwijderen?`,
      body: "De look verdwijnt. De kledingstukken zelf blijven gewoon in je kast.",
      confirmLabel: "Verwijderen",
      danger: true,
    });
    if (!ok) return;
    await api.deleteOutfit(outfit.id);
    load();
  }

  async function wear(outfit: Outfit) {
    try {
      await api.logWear(outfit.id, TODAY());
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  function toggleItem(id: number) {
    setDraft((d) =>
      d === null
        ? d
        : {
            ...d,
            itemIds: d.itemIds.includes(id)
              ? d.itemIds.filter((x) => x !== id)
              : [...d.itemIds, id],
          },
    );
  }

  return (
    <>
      <div className="topbar">
        <h1>
          Looks {outfits.length > 0 && <span className="muted">· {outfits.length}</span>}
        </h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}

        {canEdit && draft === null && (
          <button className="btn-primary btn-block" onClick={() => setDraft(emptyDraft())}>
            + Nieuwe look samenstellen
          </button>
        )}

        {canEdit && draft === null && currentId && (
          <AutofillCard wardrobeId={currentId} onChanged={load} />
        )}

        {draft !== null && (
          <div className="card" style={{ padding: 16 }}>
            <h2 style={{ marginTop: 0 }}>{draft.id === null ? "Nieuwe look" : "Look bewerken"}</h2>
            <div className="field">
              <label>Naam *</label>
              <input
                value={draft.name}
                placeholder="Bijv. Nette dinsdag"
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>

            <div className="field">
              <label>Kledingstukken * ({draft.itemIds.length} gekozen)</label>
              <div className="outfit-strip">
                {items.map((item) => {
                  const src = photoUrl(item, true);
                  const on = draft.itemIds.includes(item.id);
                  return (
                    <button
                      type="button"
                      key={item.id}
                      className="outfit-thumb"
                      title={`${item.name} · ${item.category}`}
                      style={{
                        outline: on ? "2px solid var(--primary)" : "none",
                        opacity: on ? 1 : 0.6,
                      }}
                      onClick={() => toggleItem(item.id)}
                    >
                      {src ? <img src={src} alt="" loading="lazy" /> : <span className="outfit-noimg">👕</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            <TagPicker
              label="Gelegenheid"
              options={occasions.map((o) => o.name)}
              value={draft.occasions}
              onChange={(v) => setDraft({ ...draft, occasions: v })}
            />
            <TagPicker
              label="Weer"
              hint="Hierop kiest 'Vandaag' welke look bij het weer past."
              options={WEATHER_TAGS}
              value={draft.weather}
              onChange={(v) => setDraft({ ...draft, weather: v })}
            />
            <TagPicker
              label="Seizoen"
              options={SEASONS}
              value={draft.seasons}
              onChange={(v) => setDraft({ ...draft, seasons: v })}
            />
            <TagPicker
              label="Stijl"
              options={[]}
              value={draft.styles}
              onChange={(v) => setDraft({ ...draft, styles: v })}
              allowCustom
            />

            <div className="field">
              <label>Notities</label>
              <textarea
                value={draft.notes}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              />
            </div>

            <div className="row" style={{ gap: 10 }}>
              <button className="btn-ghost" style={{ flex: 1 }} onClick={() => setDraft(null)}>
                Annuleren
              </button>
              <button className="btn-primary" style={{ flex: 1 }} disabled={busy} onClick={save}>
                {busy ? "Bezig…" : "Opslaan"}
              </button>
            </div>
          </div>
        )}

        {outfits.length > 0 && (
          <div className="chips wrap" style={{ marginTop: 16 }}>
            <button
              type="button"
              className={`chip ${filter === "" ? "active" : ""}`}
              onClick={() => setFilter("")}
            >
              Alle
            </button>
            {occasions.map((o) => (
              <button
                type="button"
                key={o.id}
                className={`chip ${filter === o.name ? "active" : ""}`}
                onClick={() => setFilter(o.name)}
              >
                {o.name}
              </button>
            ))}
          </div>
        )}

        {loading && <div className="spinner" />}

        {!loading && outfits.length === 0 && (
          <div className="empty">
            <div className="big">✨</div>
            <p>
              Nog geen looks. Stel er een samen, of laat de app er een voorstellen bij{" "}
              <strong>Ontdekken</strong>.
            </p>
          </div>
        )}

        {shown.map((outfit) => (
          <div
            className="card rec-card"
            id={`outfit-${outfit.id}`}
            key={outfit.id}
            style={
              highlight === outfit.id
                ? { borderColor: "var(--primary)", boxShadow: "0 0 0 1px var(--primary)" }
                : undefined
            }
          >
            <div className="rec-head">
              <span className="rec-title">{outfit.name}</span>
              {preferences?.wear_log_enabled && outfit.wear_count > 0 && (
                <span className="rec-source">{outfit.wear_count}× gedragen</span>
              )}
            </div>
            <OutfitStrip items={outfit.items} />
            {(outfit.occasions.length > 0 || outfit.weather_tags.length > 0) && (
              <div className="chips wrap">
                {outfit.occasions.map((t) => (
                  <span className="tag" key={`o-${t}`}>
                    {t}
                  </span>
                ))}
                {outfit.weather_tags.map((t) => (
                  <span className="tag" key={`w-${t}`}>
                    {t}
                  </span>
                ))}
              </div>
            )}
            {outfit.notes && <p className="rec-reason">{outfit.notes}</p>}
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              {preferences?.wear_log_enabled && (
                <button
                  className="btn-ghost"
                  disabled={outfit.last_worn === TODAY()}
                  onClick={() => wear(outfit)}
                >
                  {outfit.last_worn === TODAY() ? "✓ Vandaag gedragen" : "Vandaag gedragen"}
                </button>
              )}
              {canEdit && (
                <>
                  <button
                    className="btn-ghost"
                    onClick={() => {
                      setDraft(draftOf(outfit));
                      setParams({});
                    }}
                  >
                    Bewerken
                  </button>
                  <button className="btn-danger" onClick={() => remove(outfit)}>
                    Verwijderen
                  </button>
                </>
              )}
            </div>
          </div>
        ))}

        <AppFooter />
      </div>
    </>
  );
}
