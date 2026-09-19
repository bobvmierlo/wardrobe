import { photoUrl } from "../api";
import type { Item } from "../types";

interface Props {
  items: Item[];
  /** Thumbnail edge in pixels. The planner uses small ones, "Vandaag" big. */
  size?: number;
  onPick?: (item: Item) => void;
}

/** The garments of an outfit, side by side.
 *
 * Every screen that shows an outfit shows it this way, so what an outfit
 * "looks like" never depends on which screen you are on. */
export default function OutfitStrip({ items, size = 72, onPick }: Props) {
  if (!items.length) return <p className="muted">Nog geen kleding in deze outfit.</p>;
  return (
    <div className="outfit-strip">
      {items.map((item) => {
        const src = photoUrl(item, true);
        const body = src ? (
          <img src={src} alt="" loading="lazy" />
        ) : (
          <span className="outfit-noimg" aria-hidden="true">
            👕
          </span>
        );
        return onPick ? (
          <button
            type="button"
            key={item.id}
            className="outfit-thumb"
            style={{ width: size, height: size }}
            title={`${item.name} · ${item.category}`}
            onClick={() => onPick(item)}
          >
            {body}
          </button>
        ) : (
          <div
            key={item.id}
            className="outfit-thumb"
            style={{ width: size, height: size }}
            title={`${item.name} · ${item.category}`}
          >
            {body}
          </div>
        );
      })}
    </div>
  );
}
