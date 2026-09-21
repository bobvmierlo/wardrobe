import { photoUrl } from "../api";
import { colorHex } from "../colors";
import type { Item } from "../types";

interface Props {
  items: Item[];
  /** How many tiles to draw before the last one becomes "+3". Five fills the
   *  mosaic exactly; a planner card has room for fewer. */
  max?: number;
  /** One row of equal tiles instead of a lead and its neighbours. For a card
   *  small enough that a two-row mosaic would be four thumbnails nobody can
   *  make out. */
  compact?: boolean;
}

/** The garments of a look, as one picture instead of a row of squares.
 *
 * `OutfitStrip` puts them side by side at a fixed size, which is right when
 * the look *is* the screen. In a grid of two hundred looks it is not: the
 * squares wrap, every card ends up a different height, and nothing reads as an
 * outfit. So here the first garment leads and the rest sit beside it, and a
 * garment with no photo shows its colour rather than a shrug — the colour is
 * the thing you are scanning for anyway.
 */
export default function LookMosaic({ items, max = 5, compact = false }: Props) {
  if (!items.length) return <p className="muted">Nog geen kleding in deze look.</p>;

  // The "+3" is a tile of its own, so it costs one of the slots rather than
  // covering up a garment that would otherwise have been visible.
  const overflowing = items.length > max;
  const shown = overflowing ? items.slice(0, max - 1) : items;
  const rest = items.length - shown.length;

  return (
    <div className={`look-mosaic${compact ? " compact" : ""}`}>
      {shown.map((item, index) => {
        const src = photoUrl(item, true);
        return (
          <div
            key={item.id}
            className={`tile${index === 0 && !compact ? " lead" : ""}`}
            title={`${item.name} · ${item.category}`}
          >
            {src ? (
              <img src={src} alt="" loading="lazy" />
            ) : (
              // No photo: the colour it was tagged with is still information,
              // and a wall of identical placeholders is not.
              <span
                style={{ background: colorHex(item.color), width: "100%", height: "100%" }}
                aria-hidden="true"
              />
            )}
          </div>
        );
      })}
      {rest > 0 && (
        <div className="tile more" aria-label={`Nog ${rest} kledingstuk(ken)`}>
          +{rest}
        </div>
      )}
    </div>
  );
}
