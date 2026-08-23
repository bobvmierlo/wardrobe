import { useState } from "react";
import { Link } from "react-router-dom";
import { photoUrl } from "../api";
import { useConfirm } from "../confirm";
import type { RejectedPartner } from "../types";

interface Props {
  rejected: RejectedPartner[];
  /** Withdraw my own "nee". Only offered for pairs I rejected myself. */
  onUndo: (partner: RejectedPartner) => Promise<void>;
}

/** Combinations that were turned down, and by whom.
 *
 * Lives on a garment's own page only. It answers "waarom zie ik die
 * combinatie niet bij Outfits?" — usually because somebody said no, and one
 * "nee" is enough to block a pair however many others approved it.
 */
export default function RejectedGrid({ rejected, onUndo }: Props) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  async function undo(partner: RejectedPartner) {
    if (busy !== null) return;
    const ok = await confirm({
      title: `Je "nee" voor "${partner.item.name}" intrekken?`,
      body: "Het paar komt daarna weer langs bij Combineer om opnieuw te beoordelen.",
      confirmLabel: "Intrekken",
      danger: false,
    });
    if (!ok) return;
    setBusy(partner.item.id);
    setError(null);
    try {
      await onUndo(partner);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ongedaan maken mislukt");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {error && <div className="error">{error}</div>}
      <div className="stack">
        {rejected.map((partner) => {
          const p = partner.item;
          const src = photoUrl(p, true);
          const split = partner.approved_by.length > 0;
          return (
            <div key={p.id} className="card rejected-row">
              <Link to={`/item/${p.id}`} className="rejected-thumb" title={p.name}>
                {src ? <img src={src} alt={p.name} width={52} height={52} loading="lazy" decoding="async" /> : <span className="noimg-ico">👕</span>}
              </Link>
              <div className="rejected-meta">
                <div className="rejected-name">{p.name}</div>
                <div className="rejected-by">✕ {partner.rejected_by.join(", ")}</div>
                {split && (
                  <div className="muted" style={{ fontSize: "0.75rem" }}>
                    👍 {partner.approved_by.join(", ")} vond van wel — één "nee" blokkeert
                  </div>
                )}
              </div>
              {partner.rejected_by_me && (
                <button
                  className="btn-ghost btn-small"
                  onClick={() => undo(partner)}
                  disabled={busy !== null}
                >
                  {busy === p.id ? "Bezig…" : "↩ Ongedaan"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
