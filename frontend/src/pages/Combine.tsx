import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, OfflineError, photoUrl } from "../api";
import SwipeCard, { type SwipeCardHandle } from "../components/SwipeCard";
import AppFooter from "../components/AppFooter";
import JudgedPairList from "../components/JudgedPairList";
import SuggestionList from "../components/SuggestionList";
import ImageModal, { zoomPhoto, type ZoomPhoto } from "../components/ImageModal";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useOnline } from "../online";
import { addPending, listPending, pairKey, settlePending, type PendingVerdict } from "../pending";
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

  // A stretch of the queue, fetched ahead. The screen shows its head; having
  // the rest in hand is what lets someone keep swiping through a tunnel.
  const [queue, setQueue] = useState<Pair[]>([]);
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
  // Verdicts the service worker is holding until there is a connection again.
  const [pending, setPending] = useState<PendingVerdict[]>([]);
  const online = useOnline();
  const cardRef = useRef<SwipeCardHandle>(null);

  const pair = queue[0] ?? null;
  const pendingKeys = new Set(pending.map((p) => pairKey(p.a, p.b)));

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

  /** Fetch a fresh stretch of the queue, replacing whatever we were holding. */
  async function loadQueue(anchorId?: number) {
    if (!current) return;
    setLoading(true);
    setError(null);
    try {
      let next = await api.pairQueue(current.id, anchorId);
      // Current anchor exhausted → let the server pick a fresh anchor.
      if (next.length === 0 && anchorId != null) next = await api.pairQueue(current.id);
      // A pair judged while offline is still on the server's list until the
      // queued verdict lands; do not offer it a second time.
      const held = listPending(current.id).map((p) => pairKey(p.a, p.b));
      const fresh = next.filter((p) => !held.includes(pairKey(p.anchor.id, p.candidate.id)));
      setQueue(fresh);
      setDone(fresh.length === 0);
    } catch (e) {
      // Offline with pairs still in hand is not an error — that is the point.
      if (e instanceof OfflineError) {
        if (queue.length === 0) setError("Geen verbinding, en geen paren in voorraad.");
      } else {
        setError(e instanceof Error ? e.message : "Laden mislukt");
      }
    } finally {
      setLoading(false);
    }
  }

  /** Quietly extend the queue when it runs low, without moving the top card. */
  async function topUp(anchorId?: number) {
    if (!current || !online || queue.length > 5) return;
    try {
      const fresh = await api.pairQueue(current.id, anchorId);
      setQueue((held) => {
        const have = new Set(held.map((p) => pairKey(p.anchor.id, p.candidate.id)));
        const extra = fresh.filter((p) => {
          const key = pairKey(p.anchor.id, p.candidate.id);
          return !have.has(key) && !pendingKeys.has(key);
        });
        const grown = [...held, ...extra];
        if (grown.length > 0) setDone(false);
        return grown;
      });
    } catch {
      /* the queue in hand is what matters; topping up can wait */
    }
  }

  useEffect(() => {
    if (!current) return;
    setLast(null);
    setLastAccepted(null);
    setPending(listPending(current.id));
    refreshStats();
    refreshJudged();
    // Only honour the passed anchor on the wardrobe it came from.
    loadQueue(initialAnchor);
    // Load the system's own outfit ideas so they're ready to show alongside
    // (and after) the manual swiping.
    refreshSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  /** Send what was decided offline, now that there is a connection again.
   *
   * The service worker will replay these too — that is what carries them when
   * the app is closed. But its replay waits for the browser to announce that
   * connectivity returned, which does not happen when it was the *server* that
   * was away. So with the app open we simply send them ourselves; the API
   * stores one verdict per pair per person, so arriving twice changes nothing.
   */
  async function flushPending() {
    if (!current) return;
    for (const entry of listPending(current.id)) {
      try {
        if (entry.verdict === "skip") await api.skipPair(entry.a, entry.b);
        else await api.submitVerdict(entry.a, entry.b, entry.verdict);
      } catch {
        return; // still nothing there; keep the rest for the next attempt
      }
      setPending(settlePending(current.id, new Set([pairKey(entry.a, entry.b)])));
    }
    try {
      const landed = await api.judgedPairs(current.id);
      setJudged(landed);
      // Anything the service worker managed to replay on its own settles here.
      setPending(
        settlePending(current.id, new Set(landed.map((j) => pairKey(j.item_a.id, j.item_b.id))))
      );
      refreshStats();
      refreshSuggestions();
    } catch {
      /* the sending is what mattered; the numbers can catch up later */
    }
  }

  // Back online with decisions still in hand: send them.
  useEffect(() => {
    if (!online || !current || pending.length === 0) return;
    const timer = window.setTimeout(flushPending, 1200);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, current?.id, pending.length]);

  async function handleDecide(verdict: Verdict) {
    if (!pair || !current) return;
    const decided = pair;
    // The card leaves the moment you swipe, connection or no connection.
    setQueue((held) => held.slice(1));
    setError(null);
    try {
      await api.submitVerdict(decided.anchor.id, decided.candidate.id, verdict);
      setLast({ pair: decided, verdict });
      refreshStats();
      refreshJudged();
      // A verdict can turn an outfit into a combination, which removes it from
      // the suggestions — so those are stale now.
      refreshSuggestions();
      topUp(decided.anchor.id);
    } catch (e) {
      if (e instanceof OfflineError) {
        // Handed to the service worker; it will replay this when there is a
        // connection, even if the app is closed by then. Undoing needs the
        // server, so no undo bar until it has landed.
        setPending(
          addPending(current.id, {
            a: decided.anchor.id,
            b: decided.candidate.id,
            verdict,
          })
        );
        setLast(null);
      } else {
        setQueue((held) => [decided, ...held]); // put the card back
        setError(e instanceof Error ? e.message : "Opslaan mislukt");
      }
    }
  }

  /** Put the current pair aside: no verdict, it returns at the end of the queue. */
  async function handleSkip() {
    if (!pair || !current) return;
    const skipped = pair;
    // Locally it goes to the back, which is what the server does with it too.
    setQueue((held) => [...held.slice(1), { ...skipped, skipped: true }]);
    setLast(null); // nothing was decided, so there is nothing to undo
    try {
      await api.skipPair(skipped.anchor.id, skipped.candidate.id);
      refreshStats();
    } catch (e) {
      if (e instanceof OfflineError) {
        setPending(
          addPending(current.id, {
            a: skipped.anchor.id,
            b: skipped.candidate.id,
            verdict: "skip",
          })
        );
      } else {
        setError(e instanceof Error ? e.message : "Overslaan mislukt");
      }
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
      await loadQueue(p.anchor.id);
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
    if (!pair) await loadQueue();
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
      if (!pair) await loadQueue();
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

        {pending.length > 0 && (
          <div className="pending-bar" role="status">
            <span aria-hidden="true">⏳</span>
            <span>
              {pending.length} {pending.length === 1 ? "oordeel wacht" : "oordelen wachten"} op
              verbinding. {online ? "Ze worden nu verstuurd." : "Ze worden verstuurd zodra je weer online bent — ook als je de app sluit."}
            </span>
          </div>
        )}

        {last && (
          <div className="undo-bar">
            <span>
              {last.pair.anchor.name} + {last.pair.candidate.name}:{" "}
              <strong>{last.verdict === "yes" ? "past bij elkaar" : "past niet"}</strong>
            </span>
            {online ? (
              <button className="btn-ghost btn-small" onClick={undoLast}>
                ↩ Ongedaan maken
              </button>
            ) : (
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                Ongedaan maken kan pas weer online
              </span>
            )}
          </div>
        )}

        {loading && !pair ? (
          <div className="spinner" />
        ) : done || !pair ? (
          <div className="empty">
            <div className="big">🎉</div>
            {!online ? (
              <>
                <p>Je hebt alle paren gehad die je in voorraad had.</p>
                <p className="muted">
                  Zodra je weer verbinding hebt, haalt de app nieuwe paren op — en worden je
                  oordelen verstuurd.
                </p>
              </>
            ) : stats && stats.item_count < 2 ? (
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
