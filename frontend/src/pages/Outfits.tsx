import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import SuggestionList from "../components/SuggestionList";
import { SEASONS, type Item, type OutfitPartner, type OutfitSuggestion } from "../types";

type Tab = "browse" | "suggest";

export default function Outfits() {
  const [tab, setTab] = useState<Tab>("browse");
  const [items, setItems] = useState<Item[]>([]);
  const [selected, setSelected] = useState<Item | null>(null);
  const [partners, setPartners] = useState<OutfitPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPartners, setLoadingPartners] = useState(false);

  // filters
  const [fCategory, setFCategory] = useState("");
  const [fSeason, setFSeason] = useState("");
  const [fColor, setFColor] = useState("");

  // suggestions
  const [suggestions, setSuggestions] = useState<OutfitSuggestion[]>([]);
  const [loadingSug, setLoadingSug] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.listItems();
        setItems(list);
        if (list.length) setSelected(list[0]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoadingPartners(true);
    api
      .outfitsFor(selected.id)
      .then(setPartners)
      .finally(() => setLoadingPartners(false));
  }, [selected]);

  useEffect(() => {
    if (tab !== "suggest" || suggestions.length) return;
    setLoadingSug(true);
    api
      .suggestions()
      .then(setSuggestions)
      .finally(() => setLoadingSug(false));
  }, [tab, suggestions.length]);

  const categories = useMemo(
    () => Array.from(new Set(items.map((i) => i.category))).sort((a, b) => a.localeCompare(b)),
    [items]
  );
  const colors = useMemo(
    () => Array.from(new Set(items.map((i) => i.color).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b)),
    [items]
  );

  const visibleItems = useMemo(() => {
    return items.filter((i) => {
      if (fCategory && i.category !== fCategory) return false;
      if (fColor && (i.color ?? "") !== fColor) return false;
      if (fSeason) {
        const ss = i.seasons;
        // No season set, or "Alle seizoenen", matches any filter.
        if (ss.length && !ss.includes("Alle seizoenen") && !ss.includes(fSeason)) return false;
      }
      return true;
    });
  }, [items, fCategory, fColor, fSeason]);

  // Keep the selected item valid within the current filter.
  useEffect(() => {
    if (tab !== "browse") return;
    if (visibleItems.length === 0) {
      setSelected(null);
    } else if (!selected || !visibleItems.some((i) => i.id === selected.id)) {
      setSelected(visibleItems[0]);
    }
  }, [visibleItems, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const anyFilter = fCategory || fSeason || fColor;

  return (
    <>
      <div className="topbar">
        <h1>Outfits</h1>
      </div>
      <div className="content">
        <div className="seg">
          <button className={`seg-btn ${tab === "browse" ? "active" : ""}`} onClick={() => setTab("browse")}>
            Per stuk
          </button>
          <button className={`seg-btn ${tab === "suggest" ? "active" : ""}`} onClick={() => setTab("suggest")}>
            ✨ Suggesties
          </button>
        </div>

        {loading ? (
          <div className="spinner" />
        ) : items.length === 0 ? (
          <div className="empty">
            <div className="big">✨</div>
            <p>Nog geen kledingstukken. Voeg eerst wat toe.</p>
          </div>
        ) : tab === "suggest" ? (
          <SuggestTab loading={loadingSug} suggestions={suggestions} />
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Kies een stuk om te zien waarmee het (goedgekeurd) combineert.
            </p>

            <div className="filters">
              <select value={fCategory} onChange={(e) => setFCategory(e.target.value)}>
                <option value="">Alle categorieën</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select value={fSeason} onChange={(e) => setFSeason(e.target.value)}>
                <option value="">Alle seizoenen</option>
                {SEASONS.filter((s) => s !== "Alle seizoenen").map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <select value={fColor} onChange={(e) => setFColor(e.target.value)}>
                <option value="">Alle kleuren</option>
                {colors.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              {anyFilter && (
                <button className="btn-ghost" onClick={() => { setFCategory(""); setFSeason(""); setFColor(""); }}>
                  Wis filters
                </button>
              )}
            </div>

            {visibleItems.length === 0 ? (
              <div className="empty">
                <p className="muted">Geen kledingstukken passen bij deze filters.</p>
              </div>
            ) : (
              <>
                <div className="pick-strip">
                  {visibleItems.map((it) => {
                    const s = photoUrl(it, true);
                    const active = selected?.id === it.id;
                    return (
                      <button
                        key={it.id}
                        onClick={() => setSelected(it)}
                        className={`pick-thumb ${active ? "active" : ""}`}
                        title={it.name}
                      >
                        {s ? (
                          <img src={s} alt={it.name} />
                        ) : (
                          <span className="noimg-ico">👕</span>
                        )}
                      </button>
                    );
                  })}
                </div>

                {selected && (
                  <div className="anchor-band" style={{ marginBottom: 16 }}>
                    {photoUrl(selected, true) ? (
                      <img src={photoUrl(selected, true)!} alt={selected.name} />
                    ) : (
                      <div className="noimg-sm">👕</div>
                    )}
                    <div>
                      <div style={{ fontWeight: 700 }}>{selected.name}</div>
                      <div className="muted" style={{ fontSize: "0.8rem" }}>{selected.category}</div>
                    </div>
                    <Link to={`/item/${selected.id}`} className="pill" style={{ marginLeft: "auto" }}>
                      Details
                    </Link>
                  </div>
                )}

                {loadingPartners ? (
                  <div className="spinner" />
                ) : partners.length === 0 ? (
                  <div className="empty">
                    <p className="muted">Nog geen goedgekeurde combinaties voor dit stuk.</p>
                    <Link to="/combine" state={{ anchorId: selected?.id }} className="btn-primary cta-link">
                      💞 Ga combineren
                    </Link>
                  </div>
                ) : (
                  <div className="grid">
                    {partners.map(({ item: p, approved_by }) => {
                      const s = photoUrl(p, true);
                      return (
                        <Link to={`/item/${p.id}`} key={p.id} className="card">
                          {s ? <img className="thumb" src={s} alt={p.name} /> : <div className="noimg">👕</div>}
                          <div className="meta">
                            <div className="name">{p.name}</div>
                            <div className="sub">👍 {approved_by.join(", ")}</div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}
        <AppFooter />
      </div>
    </>
  );
}

function SuggestTab({ loading, suggestions }: { loading: boolean; suggestions: OutfitSuggestion[] }) {
  if (loading) return <div className="spinner" />;
  if (suggestions.length === 0) {
    return (
      <div className="empty">
        <div className="big">🎨</div>
        <p>Nog geen suggesties.</p>
        <p className="muted">Voeg wat kleuren en seizoenen aan je kledingstukken toe voor betere combinaties.</p>
      </div>
    );
  }
  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        Automatische combinaties op basis van kleur en seizoen. Afgekeurde paren worden nooit voorgesteld.
      </p>
      <SuggestionList suggestions={suggestions} />
    </>
  );
}
