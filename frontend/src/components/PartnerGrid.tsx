import { useState } from "react";
import { Link } from "react-router-dom";
import { useConfirm } from "../confirm";
import { photoUrl } from "../api";
import type { OutfitPartner } from "../types";

interface Props {
  partners: OutfitPartner[];
  /** When given, each combination can be taken back (the current user's vote). */
  onUndo?: (partner: OutfitPartner) => Promise<void>;
}

/** The approved combinations for one garment, optionally undoable.
 *
 * Undoing only withdraws *your* approval. A combination another member also
 * approved stays, which is why the button says "mijn goedkeuring" rather than
 * promising the combination disappears.
 */
export default function PartnerGrid({ partners, onUndo }: Props) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  async function undo(partner: OutfitPartner) {
    if (!onUndo || busy !== null) return;
    const ok = await confirm({
      title: `Combinatie met "${partner.item.name}" ongedaan maken?`,
      body: "Alleen jouw goedkeuring wordt ingetrokken. Keurde iemand anders de combinatie ook goed, dan blijft die staan.",
      confirmLabel: "Ongedaan maken",
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
      <div className="grid">
        {partners.map((partner) => {
          const p = partner.item;
          const src = photoUrl(p, true);
          return (
            <div key={p.id} className="card partner-card">
              <Link to={`/item/${p.id}`} className="partner-link">
                {src ? <img className="thumb" src={src} alt={p.name} loading="lazy" decoding="async" /> : <div className="noimg">👕</div>}
                <div className="meta">
                  <div className="name">{p.name}</div>
                  <div className="sub">👍 {partner.approved_by.join(", ")}</div>
                </div>
              </Link>
              {onUndo && (
                <button
                  type="button"
                  className="partner-undo"
                  onClick={() => undo(partner)}
                  disabled={busy !== null}
                  title="Mijn goedkeuring voor deze combinatie intrekken"
                  aria-label={`Combinatie met ${p.name} ongedaan maken`}
                >
                  {busy === p.id ? "…" : "↩"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
