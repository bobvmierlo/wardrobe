import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import HScroll from "../components/HScroll";
import PartnerGrid from "../components/PartnerGrid";
import SuggestionList from "../components/SuggestionList";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import { SEASONS, type Item, type OutfitPartner, type OutfitSuggestion } from "../types";

type Tab = "browse" | "suggest";

export default function Outfits() {
  const { current } = useWardrobe();
  const currentId = current?.id;
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
  // The outfit just adopted, confirmed here because it drops out of the list.
  const [accepted, setAccepted] = useState<OutfitSuggestion | null>(null);

  // The strip can be much wider than the screen, so scroll the chosen thumb
  // back into view whenever it changes — otherwise the marked item is off to
  // the side and it stops being obvious which one is selected.
  const activeThumb = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!currentId) return;
    // Reset when switching wardrobes so nothing from another kast lingers.
    setSuggestions([]);
    setAccepted(null);
    setLoading(true);
    (async () => {
      try {
        const list = await api.listItems(currentId);
        setItems(list);
        setSelected(list.length ? list[0] : null);
      } finally {
        setLoading(false);
      }
    })();
  }, [currentId]);

  useEffect(() => {
    activeThumb.current?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [selected?.id, tab]);

  useEffect(() => {
    if (!selected) return;
    setLoadingPartners(true);
    api
      .outfitsFor(selected.id)
      .then(setPartners)
      .finally(() => setLoadingPartners(false));
  }, [selected]);

  useEffect(() => {
    if (tab !== "suggest" || suggestions.length || !currentId) return;
    setLoadingSug(true);
    api
      .suggestions(currentId)
      .then(setSuggestions)
      .finally(() => setLoadingSug(false));
  }, [tab, suggestions.length, currentId]);

  /** Withdraw my approval of a combination shown for the selected garment. */
  async function undoCombination(partner: OutfitPartner) {
    if (!selected || !current) return;
    await api.resetPair(selected.id, partner.item.id);
    setPartners(await api.outfitsFor(selected.id));
    // The pair is up for judging again, so it may resurface as a suggestion.
    setSuggestions(await api.suggestions(current.id));
  }

  /** Adopt a suggested outfit as a real combination, then refresh what changed. */
  async function acceptSuggestion(suggestion: OutfitSuggestion) {
    if (!current) return;
    await api.acceptSuggestion(suggestion.items.map((it) => it.id));
    setAccepted(suggestion);
    setSuggestions(await api.suggestions(current.id));
    if (selected) setPartners(await api.outfitsFor(selected.id));
  }

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
        <WardrobeSwitcher />
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
          <SuggestTab
            loading={loadingSug}
            suggestions={suggestions}
            accepted={accepted}
            onAccept={acceptSuggestion}
          />
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
                <div className="pick-label">Kies het stuk waar je omheen bouwt</div>
                <HScroll className="pick-strip" label="Kies een kledingstuk">
                  {visibleItems.map((it) => {
                    const s = photoUrl(it, true);
                    const active = selected?.id === it.id;
                    return (
                      <button
                        key={it.id}
                        ref={active ? activeThumb : undefined}
                        onClick={() => setSelected(it)}
                        className={`pick-card ${active ? "active" : ""}`}
                        title={it.name}
                        aria-pressed={active}
                      >
                        <span className="pick-photo">
                          {s ? (
                            <img src={s} alt={it.name} width={104} height={104} loading="lazy" decoding="async" />
                          ) : (
                            <span className="noimg-ico">👕</span>
                          )}
                          {active && <span className="pick-check" aria-hidden="true">✓</span>}
                        </span>
                        <span className="pick-name">{it.name}</span>
                      </button>
                    );
                  })}
                </HScroll>

                {selected && (
                  <div className="anchor-band selected-band">
                    {photoUrl(selected, true) ? (
                      <img src={photoUrl(selected, true)!} alt={selected.name} width={64} height={64} decoding="async" />
                    ) : (
                      <div className="noimg-sm">👕</div>
                    )}
                    <div>
                      <div className="muted" style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        Gekozen stuk
                      </div>
                      <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>{selected.name}</div>
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        {selected.category}
                        {selected.color ? ` · ${selected.color}` : ""}
                      </div>
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
                  <PartnerGrid partners={partners} onUndo={undoCombination} />
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

function SuggestTab({
  loading,
  suggestions,
  accepted,
  onAccept,
}: {
  loading: boolean;
  suggestions: OutfitSuggestion[];
  accepted: OutfitSuggestion | null;
  onAccept: (suggestion: OutfitSuggestion) => Promise<void>;
}) {
  if (loading) return <div className="spinner" />;
  const confirmation = accepted && (
    <div className="undo-bar" style={{ marginBottom: 12 }}>
      <span>
        ✓ Opgeslagen als combinatie:{" "}
        <strong>{accepted.items.map((it) => it.name).join(" + ")}</strong>
      </span>
      <span className="muted" style={{ fontSize: "0.78rem" }}>
        Terug te draaien bij "Per stuk"
      </span>
    </div>
  );
  if (suggestions.length === 0) {
    return (
      <>
        {confirmation}
        <div className="empty">
          <div className="big">🎨</div>
          <p>Nog geen suggesties.</p>
          <p className="muted">
            Voeg wat kleuren en seizoenen aan je kledingstukken toe voor betere combinaties,
            of neem eerst een besluit over de combinaties die je al hebt gezien.
          </p>
        </div>
      </>
    );
  }
  return (
    <>
      {confirmation}
      <p className="muted" style={{ marginTop: 0 }}>
        Automatische combinaties op basis van kleur en seizoen. Combinaties die je al hebt
        goedgekeurd of afgekeurd staan er niet tussen — bevalt er een? Sla 'm op.
      </p>
      <SuggestionList suggestions={suggestions} onAccept={onAccept} />
    </>
  );
}
