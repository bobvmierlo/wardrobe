import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import AutofillCard from "../components/AutofillCard";
import FilterBar from "../components/FilterBar";
import LookMosaic from "../components/LookMosaic";
import Modal from "../components/Modal";
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

/** Everything the list can be narrowed by, in one object. */
interface Filters {
  q: string;
  item: string;
  season: string;
  occasion: string;
  weather: string;
}

const NO_FILTERS: Filters = { q: "", item: "", season: "", occasion: "", weather: "" };

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
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [helper, setHelper] = useState(false);

  function set<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((f) => ({ ...f, [key]: value }));
  }

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

  // The vocabularies the dropdowns offer come out of the looks themselves:
  // a filter for a tag nothing carries is a dead end with a label on it.
  const options = useMemo(() => {
    const used = (pick: (o: Outfit) => string[]) =>
      [...new Set(outfits.flatMap(pick))].sort((a, b) => a.localeCompare(b, "nl"));
    return {
      seasons: SEASONS.filter((s) => used((o) => o.seasons).includes(s)),
      occasions: used((o) => o.occasions),
      weather: WEATHER_TAGS.filter((w) => used((o) => o.weather_tags).includes(w)),
      // Only garments that are actually in a look: picking one that is in none
      // can only ever answer "nothing".
      items: items
        .filter((i) => outfits.some((o) => o.items.some((x) => x.id === i.id)))
        .sort((a, b) => a.name.localeCompare(b.name, "nl")),
    };
  }, [outfits, items]);

  const shown = useMemo(() => {
    const needle = filters.q.trim().toLowerCase();
    return outfits.filter((o) => {
      if (filters.occasion && !o.occasions.includes(filters.occasion)) return false;
      if (filters.season && !o.seasons.includes(filters.season)) return false;
      if (filters.weather && !o.weather_tags.includes(filters.weather)) return false;
      if (filters.item && !o.items.some((i) => String(i.id) === filters.item)) return false;
      if (needle) {
        const hay = [o.name, o.notes ?? "", ...o.style_tags, ...o.items.map((i) => i.name)]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [outfits, filters]);

  // The search field is always on screen; the dropdowns are what the toggle
  // reveals on a phone, so it counts only those.
  const activeCount = [filters.item, filters.season, filters.occasion, filters.weather].filter(
    (v) => v !== "",
  ).length;
  const active = activeCount > 0 || filters.q.trim() !== "";

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

        {canEdit && (
          <div className="row" style={{ gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
            <button className="btn-primary" onClick={() => setDraft(emptyDraft())}>
              + Nieuwe look
            </button>
            <button className="btn-ghost" onClick={() => setHelper((v) => !v)} aria-expanded={helper}>
              {helper ? "Aanvullen verbergen" : "✨ Kast laten aanvullen"}
            </button>
          </div>
        )}

        {canEdit && helper && currentId && (
          <div style={{ marginBottom: 16 }}>
            <AutofillCard wardrobeId={currentId} onChanged={load} />
          </div>
        )}

        {outfits.length > 0 && (
          <FilterBar
            active={activeCount}
            search={
              <input
                className="search"
                placeholder="Zoek op naam, tag of kledingstuk…"
                value={filters.q}
                onChange={(e) => set("q", e.target.value)}
              />
            }
          >
            <select
              className={filters.item ? "on" : ""}
              aria-label="Kledingstuk"
              value={filters.item}
              onChange={(e) => set("item", e.target.value)}
            >
              <option value="">Alle kledingstukken</option>
              {options.items.map((i) => (
                <option key={i.id} value={String(i.id)}>
                  {i.name}
                </option>
              ))}
            </select>
            <select
              className={filters.season ? "on" : ""}
              aria-label="Seizoen"
              value={filters.season}
              onChange={(e) => set("season", e.target.value)}
            >
              <option value="">Alle seizoenen</option>
              {options.seasons.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className={filters.occasion ? "on" : ""}
              aria-label="Gelegenheid"
              value={filters.occasion}
              onChange={(e) => set("occasion", e.target.value)}
            >
              <option value="">Alle gelegenheden</option>
              {options.occasions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <select
              className={filters.weather ? "on" : ""}
              aria-label="Weertype"
              value={filters.weather}
              onChange={(e) => set("weather", e.target.value)}
            >
              <option value="">Alle weertypes</option>
              {options.weather.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </FilterBar>
        )}

        {active && (
          <div className="filter-summary">
            <span>
              {shown.length} van de {outfits.length} looks
            </span>
            <button className="btn-ghost" onClick={() => setFilters(NO_FILTERS)}>
              Filters wissen
            </button>
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

        {!loading && outfits.length > 0 && shown.length === 0 && (
          <div className="empty">
            <p>Geen looks gevonden met deze filters.</p>
            <button className="btn-ghost" onClick={() => setFilters(NO_FILTERS)}>
              Filters wissen
            </button>
          </div>
        )}

        <div className="looks-grid">
          {shown.map((outfit) => (
            <div
              className="card look-card"
              id={`outfit-${outfit.id}`}
              key={outfit.id}
              style={
                highlight === outfit.id
                  ? { borderColor: "var(--primary)", boxShadow: "0 0 0 1px var(--primary)" }
                  : undefined
              }
            >
              <LookMosaic items={outfit.items} />

              <div>
                <div className="look-title">{outfit.name}</div>
                <div className="look-sub">
                  {outfit.items.length} onderdel{outfit.items.length === 1 ? "" : "en"}
                  {preferences?.wear_log_enabled && outfit.wear_count > 0
                    ? ` · ${outfit.wear_count}× gedragen`
                    : ""}
                </div>
              </div>

              {/* Per soort, en per soort een eigen kleur: seizoen, dan waar je 'm
                  voor aantrekt (gelegenheid en weer), dan de stijlwoorden. */}
              {(outfit.seasons.length > 0 ||
                outfit.occasions.length > 0 ||
                outfit.weather_tags.length > 0 ||
                outfit.style_tags.length > 0) && (
                <div className="chips wrap">
                  {outfit.seasons.map((t) => (
                    <span className="tag plain tag-season" key={`s-${t}`}>
                      {t}
                    </span>
                  ))}
                  {outfit.occasions.map((t) => (
                    <span className="tag plain tag-context" key={`o-${t}`}>
                      {t}
                    </span>
                  ))}
                  {outfit.weather_tags.map((t) => (
                    <span className="tag plain tag-context" key={`w-${t}`}>
                      {t}
                    </span>
                  ))}
                  {outfit.style_tags.map((t) => (
                    <span className="tag plain tag-style" key={`y-${t}`}>
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {outfit.notes && <p className="rec-reason" style={{ margin: 0 }}>{outfit.notes}</p>}

              <div className="look-actions">
                {preferences?.wear_log_enabled && (
                  <button
                    className={`icon-btn ${outfit.last_worn === TODAY() ? "on" : ""}`}
                    disabled={outfit.last_worn === TODAY()}
                    title={
                      outfit.last_worn === TODAY()
                        ? "Vandaag al afgevinkt"
                        : "Vandaag gedragen"
                    }
                    aria-label="Vandaag gedragen"
                    onClick={() => wear(outfit)}
                  >
                    ✓
                  </button>
                )}
                {canEdit && (
                  <>
                    <button
                      className="icon-btn"
                      title="Bewerken"
                      aria-label={`"${outfit.name}" bewerken`}
                      onClick={() => {
                        setDraft(draftOf(outfit));
                        setParams({});
                      }}
                    >
                      ✎
                    </button>
                    <button
                      className="icon-btn danger"
                      title="Verwijderen"
                      aria-label={`"${outfit.name}" verwijderen`}
                      onClick={() => remove(outfit)}
                    >
                      🗑
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        <AppFooter />
      </div>

      {/* A dialog, not a panel at the top of the page. Editing the two
          hundredth look used to open a form somewhere far above where you were
          looking, which reads as "the button did nothing". */}
      {draft !== null && (
        <Modal
          wide
          title={draft.id === null ? "Nieuwe look" : "Look bewerken"}
          onClose={() => setDraft(null)}
          footer={
            <>
              <button className="btn-ghost" onClick={() => setDraft(null)}>
                Annuleren
              </button>
              <button className="btn-primary" disabled={busy} onClick={save}>
                {busy ? "Bezig…" : "Opslaan"}
              </button>
            </>
          }
        >
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

          <div className="field" style={{ marginBottom: 0 }}>
            <label>Notities</label>
            <textarea
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </div>
        </Modal>
      )}
    </>
  );
}
