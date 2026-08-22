import { useState } from "react";
import { Link } from "react-router-dom";
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

  async function undo(partner: OutfitPartner) {
    if (!onUndo || busy !== null) return;
    if (!confirm(`Combinatie met "${partner.item.name}" ongedaan maken?`)) return;
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
                {src ? <img className="thumb" src={src} alt={p.name} /> : <div className="noimg">👕</div>}
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
