import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, photoUrl } from "../api";
import SwipeCard, { type SwipeCardHandle } from "../components/SwipeCard";
import AppFooter from "../components/AppFooter";
import SuggestionList from "../components/SuggestionList";
import ImageModal from "../components/ImageModal";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import type { OutfitSuggestion, Pair, Stats } from "../types";

export default function Combine() {
  const location = useLocation() as { state?: { anchorId?: number } };
  const initialAnchor = location.state?.anchorId;
  const { current } = useWardrobe();

  const [pair, setPair] = useState<Pair | null>(null);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [suggestions, setSuggestions] = useState<OutfitSuggestion[]>([]);
  const [zoom, setZoom] = useState<string | null>(null);
  const cardRef = useRef<SwipeCardHandle>(null);

  async function refreshStats() {
    if (!current) return;
    try {
      setStats(await api.stats(current.id));
    } catch {
      /* non-critical */
    }
  }

  async function loadNext(anchorId?: number) {
    if (!current) return;
    setLoading(true);
    setError(null);
    try {
      let next = await api.nextPair(current.id, anchorId);
      // Current anchor exhausted → let the server pick a fresh anchor.
      if (!next && anchorId != null) next = await api.nextPair(current.id);
      if (next) {
        setPair(next);
        setDone(false);
      } else {
        setPair(null);
        setDone(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Laden mislukt");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!current) return;
    refreshStats();
    // Only honour the passed anchor on the wardrobe it came from.
    loadNext(initialAnchor);
    // Load the system's own outfit ideas so they're ready to show alongside
    // (and after) the manual swiping.
    api.suggestions(current.id).then(setSuggestions).catch(() => setSuggestions([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  async function handleDecide(verdict: "yes" | "no") {
    if (!pair) return;
    const anchorId = pair.anchor.id;
    try {
      await api.submitVerdict(pair.anchor.id, pair.candidate.id, verdict);
      refreshStats();
      await loadNext(anchorId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  const anchor = pair?.anchor;
  const anchorSrc = anchor ? photoUrl(anchor, true) : null;
  const pct = stats && stats.total_pairs > 0 ? Math.round((stats.judged_by_me / stats.total_pairs) * 100) : 0;

  return (
    <>
      <div className="topbar">
        <h1>Combineer</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content combine">
        {stats && stats.total_pairs > 0 && (
          <div style={{ width: "100%" }}>
            <div className="row spread" style={{ marginBottom: 6 }}>
              <span className="muted" style={{ fontSize: "0.8rem" }}>
                {stats.judged_by_me} van {stats.total_pairs} paren beoordeeld
              </span>
              <span className="muted" style={{ fontSize: "0.8rem" }}>{pct}%</span>
            </div>
            <div className="progress">
              <span style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {error && <div className="error" style={{ width: "100%" }}>{error}</div>}

        {loading && !pair ? (
          <div className="spinner" />
        ) : done || !pair ? (
          <div className="empty">
            <div className="big">🎉</div>
            {stats && stats.item_count < 2 ? (
              <>
                <p>Voeg minstens 2 kledingstukken toe om te kunnen combineren.</p>
              </>
            ) : (
              <>
                <p>Alles beoordeeld!</p>
                <p className="muted">Je hebt alle paren gehad. Voeg nieuwe stukken toe voor meer combinaties.</p>
              </>
            )}
          </div>
        ) : (
          <>
            <div className="anchor-band">
              {anchorSrc ? (
                <button
                  type="button"
                  className="anchor-thumb"
                  onClick={() => setZoom(photoUrl(anchor!) || anchorSrc)}
                  aria-label={`Vergroot foto van ${anchor!.name}`}
                >
                  <img src={anchorSrc} alt={anchor!.name} />
                  <span className="zoom-badge" aria-hidden="true">⤢</span>
                </button>
              ) : (
                <div className="noimg-sm">👕</div>
              )}
              <div>
                <div className="muted" style={{ fontSize: "0.75rem" }}>Past dit bij…</div>
                <div style={{ fontWeight: 700 }}>{anchor!.name}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>{anchor!.category}</div>
              </div>
            </div>

            <div className="deck">
              <SwipeCard key={pair.candidate.id} ref={cardRef} item={pair.candidate} onDecide={handleDecide} />
            </div>

            <div className="swipe-actions">
              <button className="circle-btn no" onClick={() => cardRef.current?.swipe("no")} aria-label="Combineert niet">
                ✕
              </button>
              <button className="circle-btn yes" onClick={() => cardRef.current?.swipe("yes")} aria-label="Combineert goed">
                ♥
              </button>
            </div>
            <p className="muted center" style={{ fontSize: "0.8rem" }}>
              Swipe naar rechts als het combineert, naar links als het niet past.
            </p>
          </>
        )}

        {suggestions.length > 0 && (
          <div style={{ width: "100%", marginTop: 28 }}>
            <div className="row spread" style={{ marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>✨ Suggesties van het systeem</h3>
            </div>
            <p className="muted" style={{ marginTop: 0, fontSize: "0.82rem" }}>
              Automatisch samengesteld op kleur en seizoen — een handig startpunt terwijl je beoordeelt.
            </p>
            <SuggestionList suggestions={suggestions} />
          </div>
        )}

        <AppFooter />
      </div>

      {zoom && <ImageModal src={zoom} alt="Kledingstuk" onClose={() => setZoom(null)} />}
    </>
  );
}
