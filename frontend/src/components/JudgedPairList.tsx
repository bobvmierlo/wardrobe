import { useState } from "react";
import { Link } from "react-router-dom";
import { photoUrl } from "../api";
import type { Item, JudgedPair } from "../types";

interface Props {
  pairs: JudgedPair[];
  /** Undo the current user's verdict for this pair. */
  onUndo: (pair: JudgedPair) => Promise<void>;
}

function key(pair: JudgedPair): string {
  return `${pair.item_a.id}-${pair.item_b.id}`;
}

function Thumb({ item }: { item: Item }) {
  const src = photoUrl(item, true);
  return (
    <Link to={`/item/${item.id}`} className="judged-thumb" title={item.name}>
      {src ? <img src={src} alt={item.name} width={46} height={46} loading="lazy" decoding="async" /> : <span className="noimg-ico">👕</span>}
    </Link>
  );
}

/** Everything the current user has judged, each row undoable.
 *
 * Shows the other members' verdicts too, because a combination only counts as
 * approved when nobody said no — so undoing your own "nee" may be what makes
 * an outfit appear, and undoing your "ja" may not remove it.
 */
export default function JudgedPairList({ pairs, onUndo }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function undo(pair: JudgedPair) {
    if (busy) return;
    setBusy(key(pair));
    setError(null);
    try {
      await onUndo(pair);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ongedaan maken mislukt");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      {error && <div className="error">{error}</div>}
      {pairs.map((pair) => {
        const others = pair.votes.filter((v) => v.verdict !== pair.my_verdict);
        return (
          <div key={key(pair)} className="card judged-row">
            <div className="judged-items">
              <Thumb item={pair.item_a} />
              <span className="judged-plus">+</span>
              <Thumb item={pair.item_b} />
            </div>
            <div className="judged-meta">
              <div className="judged-names">
                {pair.item_a.name} + {pair.item_b.name}
              </div>
              <div className={`judged-verdict ${pair.my_verdict}`}>
                {pair.my_verdict === "yes" ? "♥ Jij: past bij elkaar" : "✕ Jij: past niet"}
              </div>
              {others.length > 0 && (
                <div className="muted" style={{ fontSize: "0.75rem" }}>
                  {others
                    .map((v) => `${v.display_name}: ${v.verdict === "yes" ? "past" : "past niet"}`)
                    .join(" · ")}
                </div>
              )}
            </div>
            <button
              className="btn-ghost btn-small"
              onClick={() => undo(pair)}
              disabled={busy !== null}
            >
              {busy === key(pair) ? "Bezig…" : "↩ Ongedaan"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
