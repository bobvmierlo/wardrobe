import { useEffect, useState, type ReactNode } from "react";
import { photoUrl } from "../api";
import type { Item } from "../types";

/** One photo in the viewer: the image plus whose it is. */
export interface ZoomPhoto {
  src: string | null;
  name: string;
  /** Small line under the name — category, brand, colour. */
  sub?: string;
  /** Short label above the name, e.g. "Past dit bij". */
  tag?: string;
}

/** A garment as the viewer wants it: the full photo (the thumbnail is only a
 *  400px fallback) and the same descriptive line the rest of the app shows. */
export function zoomPhoto(item: Item, tag?: string): ZoomPhoto {
  return {
    src: photoUrl(item) ?? photoUrl(item, true),
    name: item.name,
    sub: [item.category, item.brand, item.color].filter(Boolean).join(" · "),
    tag,
  };
}

const STACK_KEY = "wardrobe.compare.stacked";

/** The layout chosen last time, so the preference outlives one comparison. */
function storedStacked(): boolean {
  try {
    return localStorage.getItem(STACK_KEY) === "1";
  } catch {
    return false;
  }
}

interface Props {
  /** One photo enlarges it; two or more show them side by side to compare. */
  photos: ZoomPhoto[];
  onClose: () => void;
  /** Buttons under the photos, so a choice can be made without closing first. */
  actions?: ReactNode;
}

/** A full-screen image viewer for one garment or a whole comparison.
 *
 * Click the backdrop or press Escape to close. With more than one photo the
 * images are shown at the same size next to each other — comparing colours is
 * what this viewer is for, and that only works if neither side is the small one.
 */
export default function ImageModal({ photos, onClose, actions }: Props) {
  // Side by side is the point, but on a narrow screen a portrait photo gets
  // bigger when the two are stacked instead — so the choice stays with the user.
  const [stacked, setStacked] = useState(storedStacked);

  function toggleLayout() {
    setStacked((v) => {
      try {
        localStorage.setItem(STACK_KEY, v ? "0" : "1");
      } catch {
        /* private mode: the choice just does not outlive this visit */
      }
      return !v;
    });
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const comparing = photos.length > 1;

  return (
    <div
      className={`img-modal${comparing ? " comparing" : ""}`}
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <button type="button" className="img-modal-close" onClick={onClose} aria-label="Sluiten">
        ✕
      </button>
      {comparing && (
        <button
          type="button"
          className="img-modal-layout"
          onClick={(e) => {
            e.stopPropagation();
            toggleLayout();
          }}
          aria-label={stacked ? "Naast elkaar zetten" : "Onder elkaar zetten"}
          title={stacked ? "Naast elkaar" : "Onder elkaar"}
        >
          {stacked ? "⇄" : "⇅"}
        </button>
      )}

      <div className={`compare-stage${stacked ? " stacked" : ""}`}>
        {photos.map((photo, idx) => (
          <figure key={idx} className="compare-fig" onClick={(e) => e.stopPropagation()}>
            {photo.src ? (
              <img src={photo.src} alt={photo.name} decoding="async" />
            ) : (
              <div className="noimg-lg">👕</div>
            )}
            <figcaption>
              {photo.tag && <span className="lbl">{photo.tag}</span>}
              <span className="name">{photo.name}</span>
              {photo.sub && <span className="sub">{photo.sub}</span>}
            </figcaption>
          </figure>
        ))}
      </div>

      {actions && (
        <div className="img-modal-actions" onClick={(e) => e.stopPropagation()}>
          {actions}
        </div>
      )}
    </div>
  );
}
