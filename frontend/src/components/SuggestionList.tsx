import { useState } from "react";
import { Link } from "react-router-dom";
import { photoUrl } from "../api";
import HScroll from "./HScroll";
import ImageModal, { zoomPhoto, type ZoomPhoto } from "./ImageModal";
import type { OutfitSuggestion } from "../types";

interface Props {
  suggestions: OutfitSuggestion[];
  /** When given, each suggestion can be adopted as a real combination.
   *  Left out on screens where that would not make sense (or for viewers). */
  onAccept?: (suggestion: OutfitSuggestion) => Promise<void>;
}

/** Renders the system's automatic outfit suggestions as a list of cards.
 *
 * Only suggestions that are *not* yet a combination reach this list — the API
 * leaves out anything already approved or rejected — so "opslaan als combinatie"
 * can never overwrite a decision that was already made.
 *
 * The thumbnails are too small to judge a colour on, so every photo (and the
 * button under the card) opens the whole outfit full screen, at one size.
 */
export default function SuggestionList({ suggestions, onAccept }: Props) {
  // Only which card is being saved: an accepted suggestion drops out of the
  // list the moment the parent reloads it (the API no longer offers it), so
  // confirming it is the parent's job, not this card's.
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<ZoomPhoto[] | null>(null);

  async function accept(suggestion: OutfitSuggestion, idx: number) {
    if (!onAccept || busy !== null) return;
    setBusy(idx);
    setError(null);
    try {
      await onAccept(suggestion);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      {error && <div className="error">{error}</div>}
      {suggestions.map((s, idx) => {
        const names = s.items.map((it) => it.name).join(" en ");
        const open = () => setZoom(s.items.map((it) => zoomPhoto(it)));
        return (
          <div key={idx} className="card suggest-card">
            <HScroll className="suggest-row" arrows={false}>
              {s.items.map((it) => {
                const src = photoUrl(it, true);
                return (
                  <div key={it.id} className="suggest-item">
                    <button
                      type="button"
                      className="suggest-photo"
                      onClick={open}
                      aria-label={`Bekijk ${names} groot`}
                      title="Groot bekijken"
                    >
                      {src ? (
                        <img src={src} alt={it.name} width={104} height={104} loading="lazy" decoding="async" />
                      ) : (
                        <span className="noimg-ico">👕</span>
                      )}
                      <span className="zoom-badge" aria-hidden="true">⤢</span>
                    </button>
                    <Link to={`/item/${it.id}`} title={it.name}>
                      {it.name}
                    </Link>
                  </div>
                );
              })}
            </HScroll>
            <div className="suggest-reason">💡 {s.reason}</div>
            <div className="suggest-actions">
              <button className="btn-ghost btn-small" onClick={open}>
                ⤢ Groot bekijken
              </button>
              {onAccept && (
                <button
                  className="btn-primary btn-small"
                  onClick={() => accept(s, idx)}
                  disabled={s.already_combined || busy !== null}
                >
                  {busy === idx ? "Bezig…" : "♥ Opslaan als combinatie"}
                </button>
              )}
            </div>
          </div>
        );
      })}
      {zoom && <ImageModal photos={zoom} onClose={() => setZoom(null)} />}
    </div>
  );
}
