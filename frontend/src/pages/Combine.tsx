import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, photoUrl } from "../api";
import SwipeCard, { type SwipeCardHandle } from "../components/SwipeCard";
import AppFooter from "../components/AppFooter";
import JudgedPairList from "../components/JudgedPairList";
import SuggestionList from "../components/SuggestionList";
import ImageModal, { zoomPhoto, type ZoomPhoto } from "../components/ImageModal";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import type { JudgedPair, OutfitSuggestion, Pair, Stats, Verdict } from "../types";

/** How the pair is shown: one card at a time, or both photos at equal size. */
type CombineView = "deck" | "side";

const VIEW_KEY = "wardrobe.combine.view";

/** The view chosen last time — comparing is a habit, not a per-pair decision. */
function storedView(): CombineView {
  try {
    return localStorage.getItem(VIEW_KEY) === "side" ? "side" : "deck";
  } catch {
    return "deck";
  }
}

/** The pair the user last decided on, so a mistake can be taken back at once. */
interface LastDecision {
  pair: Pair;
  verdict: Verdict;
}

/** Whether a swiped pair and a judged pair are the same two garments. */
function samePair(pair: Pair, judged: JudgedPair): boolean {
  const swiped = [pair.anchor.id, pair.candidate.id].sort().join("-");
  const listed = [judged.item_a.id, judged.item_b.id].sort().join("-");
  return swiped === listed;
}

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
  const [judged, setJudged] = useState<JudgedPair[]>([]);
  const [showJudged, setShowJudged] = useState(false);
  const [last, setLast] = useState<LastDecision | null>(null);
  // The outfit just adopted from the suggestions, so it can be confirmed and
  // taken back — it vanishes from the list the moment it becomes a combination.
  const [lastAccepted, setLastAccepted] = useState<OutfitSuggestion | null>(null);
  // The photos currently blown up full screen: one garment, or both of them
  // next to each other.
  const [zoom, setZoom] = useState<ZoomPhoto[] | null>(null);
  const [view, setView] = useState<CombineView>(storedView);
  const cardRef = useRef<SwipeCardHandle>(null);

  function chooseView(next: CombineView) {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* private mode: the choice just does not outlive this visit */
    }
  }

  async function refreshStats() {
    if (!current) return;
    try {
      setStats(await api.stats(current.id));
    } catch {
      /* non-critical */
    }
  }

  async function refreshSuggestions() {
    if (!current) return;
    try {
      setSuggestions(await api.suggestions(current.id));
    } catch {
      setSuggestions([]);
    }
  }

  async function refreshJudged() {
    if (!current) return;
    try {
      setJudged(await api.judgedPairs(current.id));
    } catch {
      setJudged([]);
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
    setLast(null);
    setLastAccepted(null);
    refreshStats();
    refreshJudged();
    // Only honour the passed anchor on the wardrobe it came from.
    loadNext(initialAnchor);
    // Load the system's own outfit ideas so they're ready to show alongside
    // (and after) the manual swiping.
    refreshSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  async function handleDecide(verdict: Verdict) {
    if (!pair) return;
    const decided = pair;
    try {
      await api.submitVerdict(decided.anchor.id, decided.candidate.id, verdict);
      setLast({ pair: decided, verdict });
      refreshStats();
      refreshJudged();
      // A verdict can turn an outfit into a combination, which removes it from
      // the suggestions — so those are stale now.
      refreshSuggestions();
      await loadNext(decided.anchor.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    }
  }

  /** Put the current pair aside: no verdict, it returns at the end of the queue. */
  async function handleSkip() {
    if (!pair) return;
    const skipped = pair;
    try {
      await api.skipPair(skipped.anchor.id, skipped.candidate.id);
      setLast(null); // nothing was decided, so there is nothing to undo
      refreshStats();
      await loadNext(skipped.anchor.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Overslaan mislukt");
    }
  }

  /** Take back the verdict just given — the pair comes straight back. */
  async function undoLast() {
    if (!last) return;
    const { pair: p } = last;
    try {
      await api.resetPair(p.anchor.id, p.candidate.id);
      setLast(null);
      refreshStats();
      refreshJudged();
      refreshSuggestions();
      await loadNext(p.anchor.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ongedaan maken mislukt");
    }
  }

  /** Undo any earlier verdict, from the list of everything already judged. */
  async function undoJudged(judgedPair: JudgedPair) {
    await api.resetPair(judgedPair.item_a.id, judgedPair.item_b.id);
    // If that was also the pair the undo bar is offering, the bar is stale.
    if (last && samePair(last.pair, judgedPair)) setLast(null);
    await Promise.all([refreshStats(), refreshJudged(), refreshSuggestions()]);
    // Nothing was left to swipe, but there is now.
    if (!pair) await loadNext();
  }

  async function acceptSuggestion(suggestion: OutfitSuggestion) {
    await api.acceptSuggestion(suggestion.items.map((it) => it.id));
    setLastAccepted(suggestion);
    await Promise.all([refreshStats(), refreshJudged(), refreshSuggestions()]);
  }

  /** Take back a whole adopted outfit: every pair in it goes back to unjudged. */
  async function undoAccepted() {
    if (!lastAccepted) return;
    try {
      await api.undoSuggestion(lastAccepted.items.map((it) => it.id));
      setLastAccepted(null);
      await Promise.all([refreshStats(), refreshJudged(), refreshSuggestions()]);
      if (!pair) await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ongedaan maken mislukt");
    }
  }

  /** Blow both garments up to the same size, next to each other — colours are
   *  impossible to judge honestly while one of the two is a 54px thumbnail. */
  function openCompare() {
    if (!pair) return;
    setZoom([zoomPhoto(pair.anchor, "Past dit bij"), zoomPhoto(pair.candidate, "Combineert dit?")]);
  }

  const anchor = pair?.anchor;
  const anchorSrc = anchor ? photoUrl(anchor, true) : null;
  // The side-by-side panel is as big as the swipe card, so it needs the full
  // photo rather than the 400px thumbnail.
  const anchorPhoto = anchor ? photoUrl(anchor) ?? anchorSrc : null;
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
                {stats.skipped_by_me > 0 && ` · ${stats.skipped_by_me} overgeslagen`}
              </span>
              <span className="muted" style={{ fontSize: "0.8rem" }}>{pct}%</span>
            </div>
            <div className="progress">
              <span style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {error && <div className="error" style={{ width: "100%" }}>{error}</div>}

        {last && (
          <div className="undo-bar">
            <span>
              {last.pair.anchor.name} + {last.pair.candidate.name}:{" "}
              <strong>{last.verdict === "yes" ? "past bij elkaar" : "past niet"}</strong>
            </span>
            <button className="btn-ghost btn-small" onClick={undoLast}>
              ↩ Ongedaan maken
            </button>
          </div>
        )}

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
            <div className="view-toggle">
              <span className="muted">Weergave</span>
              <div className="seg seg-inline">
                <button
                  className={`seg-btn ${view === "deck" ? "active" : ""}`}
                  onClick={() => chooseView("deck")}
                  aria-pressed={view === "deck"}
                >
                  Eén kaart
                </button>
                <button
                  className={`seg-btn ${view === "side" ? "active" : ""}`}
                  onClick={() => chooseView("side")}
                  aria-pressed={view === "side"}
                >
                  ⇄ Naast elkaar
                </button>
              </div>
            </div>

            {view === "side" ? (
              <>
                {pair.skipped && <span className="pill skipped">⏭ Eerder overgeslagen</span>}
                <div className="combine-side">
                  <button
                    type="button"
                    className="compare-panel"
                    onClick={openCompare}
                    aria-label={`Bekijk ${anchor!.name} en ${pair.candidate.name} groot naast elkaar`}
                    title="Groot bekijken"
                  >
                    <span className="panel-photo">
                      {anchorPhoto ? (
                        <img src={anchorPhoto} alt={anchor!.name} decoding="async" />
                      ) : (
                        <span className="noimg-lg">👕</span>
                      )}
                      <span className="lbl">Past dit bij</span>
                      <span className="zoom-badge" aria-hidden="true">⤢</span>
                    </span>
                    <span className="panel-cap">
                      <span className="name">{anchor!.name}</span>
                      <span className="sub">
                        {anchor!.category}
                        {anchor!.brand ? ` · ${anchor!.brand}` : ""}
                        {anchor!.color ? ` · ${anchor!.color}` : ""}
                      </span>
                    </span>
                  </button>

                  <div className="deck">
                    <SwipeCard
                      key={pair.candidate.id}
                      ref={cardRef}
                      item={pair.candidate}
                      onDecide={handleDecide}
                      onZoom={openCompare}
                    />
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="anchor-band">
                  {anchorSrc ? (
                    <button
                      type="button"
                      className="anchor-thumb"
                      onClick={openCompare}
                      aria-label={`Bekijk ${anchor!.name} en ${pair.candidate.name} groot naast elkaar`}
                      title="Naast elkaar bekijken"
                    >
                      <img src={anchorSrc} alt={anchor!.name} width={54} height={54} decoding="async" />
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
                  {pair.skipped && <span className="pill skipped">⏭ Eerder overgeslagen</span>}
                </div>

                <div className="deck">
                  <SwipeCard
                    key={pair.candidate.id}
                    ref={cardRef}
                    item={pair.candidate}
                    onDecide={handleDecide}
                    onZoom={openCompare}
                  />
                </div>
              </>
            )}

            <div className="swipe-actions">
              <button className="circle-btn no" onClick={() => cardRef.current?.swipe("no")} aria-label="Combineert niet">
                ✕
              </button>
              <button className="circle-btn skip" onClick={handleSkip} aria-label="Sla dit paar over" title="Later beslissen">
                ⏭
              </button>
              <button className="circle-btn yes" onClick={() => cardRef.current?.swipe("yes")} aria-label="Combineert goed">
                ♥
              </button>
            </div>
            <p className="muted center" style={{ fontSize: "0.8rem" }}>
              Swipe naar rechts als het combineert, naar links als het niet past.
              Twijfel je? Sla over — dit paar komt achteraan de rij weer terug.
              {view === "side"
                ? " Tik op een foto om beide schermvullend naast elkaar te zetten."
                : " Tik op ⤢ om beide stukken even groot naast elkaar te zien."}
            </p>
          </>
        )}

        {(suggestions.length > 0 || lastAccepted) && (
          <div style={{ width: "100%", marginTop: 28 }}>
            <div className="row spread" style={{ marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>✨ Suggesties van het systeem</h3>
            </div>
            <p className="muted" style={{ marginTop: 0, fontSize: "0.82rem" }}>
              Automatisch samengesteld op kleur en seizoen. Bevalt er een? Sla 'm op als
              combinatie. Wat je al hebt goed- of afgekeurd staat er niet meer tussen.
            </p>
            {lastAccepted && (
              <div className="undo-bar" style={{ marginBottom: 12 }}>
                <span>
                  ✓ Opgeslagen als combinatie:{" "}
                  <strong>{lastAccepted.items.map((it) => it.name).join(" + ")}</strong>
                </span>
                <button className="btn-ghost btn-small" onClick={undoAccepted}>
                  ↩ Ongedaan maken
                </button>
              </div>
            )}
            {suggestions.length > 0 ? (
              <SuggestionList suggestions={suggestions} onAccept={acceptSuggestion} />
            ) : (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Geen suggesties meer — je hebt overal een besluit over genomen.
              </p>
            )}
          </div>
        )}

        {judged.length > 0 && (
          <div style={{ width: "100%", marginTop: 28 }}>
            <button
              className="btn-ghost btn-block"
              onClick={() => setShowJudged((v) => !v)}
              aria-expanded={showJudged}
            >
              {showJudged ? "▾" : "▸"} Al beoordeeld ({judged.length})
            </button>
            {showJudged && (
              <>
                <p className="muted" style={{ fontSize: "0.82rem" }}>
                  Per ongeluk iets goedgekeurd? Maak het hier ongedaan — het paar komt
                  dan gewoon weer langs om opnieuw te beoordelen.
                </p>
                <JudgedPairList pairs={judged} onUndo={undoJudged} />
              </>
            )}
          </div>
        )}

        <AppFooter />
      </div>

      {zoom && (
        <ImageModal
          photos={zoom}
          onClose={() => setZoom(null)}
          actions={
            pair && zoom.length > 1 ? (
              <>
                <button
                  className="circle-btn no"
                  onClick={() => {
                    setZoom(null);
                    handleDecide("no");
                  }}
                  aria-label="Combineert niet"
                >
                  ✕
                </button>
                <button
                  className="circle-btn skip"
                  onClick={() => {
                    setZoom(null);
                    handleSkip();
                  }}
                  aria-label="Sla dit paar over"
                >
                  ⏭
                </button>
                <button
                  className="circle-btn yes"
                  onClick={() => {
                    setZoom(null);
                    handleDecide("yes");
                  }}
                  aria-label="Combineert goed"
                >
                  ♥
                </button>
              </>
            ) : undefined
          }
        />
      )}
    </>
  );
}
