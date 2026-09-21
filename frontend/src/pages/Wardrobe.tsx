import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, photoUrl } from "../api";
import { baseColor, colorHex } from "../colors";
import AppFooter from "../components/AppFooter";
import FilterBar from "../components/FilterBar";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import { SEASONS, WEATHER_TAGS, type Item } from "../types";

/** Sort orders the list offers. Newest first is the default because the thing
 *  you just added is the thing you are most likely looking for. */
const SORTS = [
  { id: "new", label: "Nieuwste eerst" },
  { id: "name", label: "Op naam" },
  { id: "category", label: "Op categorie" },
  { id: "color", label: "Op kleur" },
] as const;

type Sort = (typeof SORTS)[number]["id"];

/** Every filter on this screen, in one object. Kept together so "wis filters"
 *  is one assignment and "is anything filtering?" is one comparison. */
interface Filters {
  q: string;
  category: string;
  season: string;
  occasion: string;
  weather: string;
  color: string;
  favOnly: boolean;
}

const NO_FILTERS: Filters = {
  q: "",
  category: "",
  season: "",
  occasion: "",
  weather: "",
  color: "",
  favOnly: false,
};

/** The counts behind one dropdown, in the order it should offer them. */
function tally(values: string[]): { value: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const value of values) {
    if (!value) continue;
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value, "nl"));
}

export default function Wardrobe() {
  const navigate = useNavigate();
  const { current, canEdit, isShared, loading: wLoading } = useWardrobe();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>("new");

  function set<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((f) => ({ ...f, [key]: value }));
  }

  async function load(wardrobeId: number) {
    setLoading(true);
    try {
      setItems(await api.listItems(wardrobeId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Laden mislukt");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (current) load(current.id);
    else if (!wLoading) setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, wLoading]);

  // What the dropdowns offer comes out of the kast itself, with the count
  // beside it: a filter for a category you own two of is worth knowing about
  // before you pick it and find two garments.
  const options = useMemo(
    () => ({
      categories: tally(items.map((i) => i.category)),
      seasons: tally(items.flatMap((i) => i.seasons)),
      occasions: tally(items.flatMap((i) => i.occasions)),
      weather: tally(items.flatMap((i) => i.weather_tags)),
      colors: tally(items.map((i) => baseColor(i.color) ?? "")),
    }),
    [items],
  );

  const filtered = useMemo(() => {
    const needle = filters.q.trim().toLowerCase();
    const rows = items.filter((i) => {
      if (filters.favOnly && !i.is_favorite) return false;
      if (filters.category && i.category !== filters.category) return false;
      if (filters.season && !i.seasons.includes(filters.season)) return false;
      if (filters.occasion && !i.occasions.includes(filters.occasion)) return false;
      if (filters.weather && !i.weather_tags.includes(filters.weather)) return false;
      if (filters.color && baseColor(i.color) !== filters.color) return false;
      if (needle) {
        // The tags are searchable too: "regen" should find the raincoat even
        // when nobody put the word in its name.
        const hay = [
          i.name,
          i.brand ?? "",
          i.color ?? "",
          i.category,
          ...i.seasons,
          ...i.occasions,
          ...i.weather_tags,
          ...i.style_tags,
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });

    const sorted = [...rows];
    if (sort === "name") sorted.sort((a, b) => a.name.localeCompare(b.name, "nl"));
    else if (sort === "category")
      sorted.sort(
        (a, b) =>
          a.category.localeCompare(b.category, "nl") || a.name.localeCompare(b.name, "nl"),
      );
    else if (sort === "color")
      sorted.sort(
        (a, b) =>
          (baseColor(a.color) ?? "zzz").localeCompare(baseColor(b.color) ?? "zzz") ||
          a.name.localeCompare(b.name, "nl"),
      );
    // "new" is the order the API already returns.
    return sorted;
  }, [items, filters, sort]);

  // How many dropdowns are narrowing things down. The search field and the
  // favourites switch are visible whatever happens, so they are not counted on
  // the button that reveals the ones that are not.
  const activeCount = [
    filters.category,
    filters.season,
    filters.occasion,
    filters.weather,
    filters.color,
  ].filter((v) => v !== "").length;
  const active = activeCount > 0 || filters.q.trim() !== "" || filters.favOnly;

  return (
    <>
      <div className="topbar">
        <h1>
          {isShared && current ? current.name : "Mijn kast"}{" "}
          {items.length > 0 && <span className="muted">· {items.length}</span>}
        </h1>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <WardrobeSwitcher />
          {!isShared && (
            <button
              className="btn-ghost"
              style={{ padding: "8px 12px", fontSize: "0.85rem", whiteSpace: "nowrap" }}
              onClick={() => navigate("/settings#delen")}
            >
              🔗 Delen
            </button>
          )}
        </div>
      </div>
      <div className="content">
        {/* The colours in this kast at a glance, and a way into them: tapping
            a band filters on it. Wardrobes are chosen by colour far more often
            than by category, and a word is a poor way to show one. */}
        {options.colors.length > 1 && (
          <div className="palette-bar" aria-hidden="true">
            {options.colors.map((c) => (
              <span
                key={c.value}
                title={`${c.value} · ${c.count}`}
                style={{
                  background: colorHex(c.value),
                  flex: c.count,
                  opacity: filters.color && filters.color !== c.value ? 0.25 : 1,
                }}
              />
            ))}
          </div>
        )}

        <FilterBar
          active={activeCount}
          search={
            <input
              className="search"
              placeholder="Zoek op naam, merk, kleur of tag…"
              value={filters.q}
              onChange={(e) => set("q", e.target.value)}
            />
          }
          extra={
            <button
              type="button"
              className={`chip ${filters.favOnly ? "active" : ""}`}
              aria-pressed={filters.favOnly}
              onClick={() => set("favOnly", !filters.favOnly)}
            >
              ★ Favoriet
            </button>
          }
        >
          <select
            className={filters.category ? "on" : ""}
            aria-label="Categorie"
            value={filters.category}
            onChange={(e) => set("category", e.target.value)}
          >
            <option value="">Alle categorieën</option>
            {options.categories.map((c) => (
              <option key={c.value} value={c.value}>
                {c.value} ({c.count})
              </option>
            ))}
          </select>
          <select
            className={filters.color ? "on" : ""}
            aria-label="Kleur"
            value={filters.color}
            onChange={(e) => set("color", e.target.value)}
          >
            <option value="">Alle kleuren</option>
            {options.colors.map((c) => (
              <option key={c.value} value={c.value}>
                {c.value} ({c.count})
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
            {SEASONS.filter((s) => options.seasons.some((o) => o.value === s)).map((s) => (
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
              <option key={o.value} value={o.value}>
                {o.value} ({o.count})
              </option>
            ))}
          </select>
          <select
            className={filters.weather ? "on" : ""}
            aria-label="Weer"
            value={filters.weather}
            onChange={(e) => set("weather", e.target.value)}
          >
            <option value="">Alle weertypes</option>
            {WEATHER_TAGS.filter((w) => options.weather.some((o) => o.value === w)).map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
          <select
            aria-label="Volgorde"
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </FilterBar>

        {/* Say what the list is showing and offer the way back. A filter left
            on in another tab is otherwise an empty kast with no explanation. */}
        {active && (
          <div className="filter-summary">
            <span>
              {filtered.length} van de {items.length} stuks
            </span>
            <button className="btn-ghost" onClick={() => setFilters(NO_FILTERS)}>
              Filters wissen
            </button>
          </div>
        )}

        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="error">{error}</div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="big">👗</div>
            {items.length === 0 ? (
              isShared ? (
                <p>Deze kast is nog leeg.</p>
              ) : (
                <>
                  <p>Je kast is nog leeg.</p>
                  <p className="muted">Tik op de knop rechtsonder om je eerste kledingstuk toe te voegen.</p>
                </>
              )
            ) : (
              <>
                <p>Geen kledingstukken gevonden.</p>
                <button className="btn-ghost" onClick={() => setFilters(NO_FILTERS)}>
                  Filters wissen
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="grid">
            {filtered.map((item) => {
              const src = photoUrl(item, true);
              return (
                <Link to={`/item/${item.id}`} key={item.id} className="card">
                  {item.is_favorite && <span className="fav">★</span>}
                  {src ? (
                    <img className="thumb" src={src} alt={item.name} loading="lazy" />
                  ) : (
                    <div className="noimg">👕</div>
                  )}
                  <div className="meta">
                    <div className="name">{item.name}</div>
                    <div className="sub">
                      {item.category}
                      {item.brand ? ` · ${item.brand}` : ""}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
        <AppFooter />
      </div>

      {canEdit && (
        <button className="fab" onClick={() => navigate("/add")} aria-label="Kledingstuk toevoegen">
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
          {/* Only on a wide screen, where the button sits in a corner of its
              own instead of under your thumb and a bare "+" is a riddle. */}
          <span className="fab-label">Toevoegen</span>
        </button>
      )}
    </>
  );
}
