import { useState } from "react";
import QrCode from "./QrCode";
import { INVITATION_STATUS_LABELS, ROLE_LABELS, type Invitation } from "../types";

/** The full link to share, built from the address this app is served on. */
function inviteUrl(invitation: Invitation): string {
  return `${window.location.origin}${invitation.path}`;
}

/**
 * A list of invitation links with the three things you do with one: copy it,
 * show it as a QR code for the phone across the table, or take it back.
 *
 * Shared by both places that hand out links — a kast being shared, and a
 * beheerder letting someone new in — because the row is the same either way.
 */
export default function InvitationLinks({
  invitations,
  onRevoke,
  onCopyFailed,
  emptyText,
}: {
  invitations: Invitation[];
  onRevoke: (invitation: Invitation) => void;
  onCopyFailed?: (message: string) => void;
  emptyText?: string;
}) {
  const [copied, setCopied] = useState<number | null>(null);
  const [showQr, setShowQr] = useState<number | null>(null);

  async function copy(invitation: Invitation) {
    try {
      await navigator.clipboard.writeText(inviteUrl(invitation));
      setCopied(invitation.id);
      setTimeout(() => setCopied((id) => (id === invitation.id ? null : id)), 2000);
    } catch {
      // Clipboard access is blocked outside a secure context (plain http on
      // your LAN, for instance) — the link is on screen to copy by hand.
      onCopyFailed?.("Kopiëren lukte niet; selecteer de link en kopieer 'm handmatig.");
    }
  }

  if (invitations.length === 0) {
    return emptyText ? (
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0 0 12px" }}>{emptyText}</p>
    ) : null;
  }

  return (
    <div className="stack" style={{ marginBottom: 12 }}>
      {invitations.map((inv) => (
        <div key={inv.id} className="invite-row">
          <div style={{ minWidth: 0 }}>
            <div>
              {inv.label || <span className="muted">Zonder omschrijving</span>}{" "}
              <span className={`status-badge ${inv.status}`}>
                {INVITATION_STATUS_LABELS[inv.status]}
              </span>
            </div>
            <div className="muted" style={{ fontSize: "0.78rem" }}>
              {inv.role ? `Rol: ${ROLE_LABELS[inv.role]}` : "Nieuw account"}
              {inv.accepted_by && ` · gebruikt door ${inv.accepted_by.display_name}`}
              {inv.status === "open" && inv.expires_at &&
                ` · geldig tot ${new Date(inv.expires_at).toLocaleDateString("nl-NL")}`}
            </div>
            {inv.status === "open" && (
              <>
                <div className="invite-link">
                  <input readOnly value={inviteUrl(inv)} onFocus={(e) => e.target.select()} />
                  <button className="btn-ghost btn-small" type="button" onClick={() => copy(inv)}>
                    {copied === inv.id ? "✓ Gekopieerd" : "Kopieer"}
                  </button>
                  <button
                    className="btn-ghost btn-small"
                    type="button"
                    aria-expanded={showQr === inv.id}
                    onClick={() => setShowQr((id) => (id === inv.id ? null : inv.id))}
                  >
                    {showQr === inv.id ? "Verberg QR" : "QR-code"}
                  </button>
                </div>
                {showQr === inv.id && (
                  <div className="qr-wrap">
                    <QrCode value={inviteUrl(inv)} />
                    <div className="muted" style={{ fontSize: "0.78rem" }}>
                      Laat 'm scannen met de camera van de telefoon.
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          {inv.status === "open" && (
            <button className="btn-danger btn-small" onClick={() => onRevoke(inv)}>
              Intrekken
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
