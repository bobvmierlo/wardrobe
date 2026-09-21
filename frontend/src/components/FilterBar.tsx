import { useState, type ReactNode } from "react";

interface Props {
  /** The search field. Always visible — it is the one filter you reach for
   *  without being asked, and it costs one row. */
  search?: ReactNode;
  /** The dropdowns. Behind a button on a phone, always out on a wide screen. */
  children: ReactNode;
  /** How many of those are actually filtering. Shown on the button, so a
   *  filter left on in another tab is never an unexplained empty list. */
  active?: number;
  /** Anything that belongs beside the dropdowns and not behind the toggle —
   *  a favourites switch, a sort order. */
  extra?: ReactNode;
}

/** A search field and a row of dropdowns, folded away where there is no room.
 *
 * Six dropdowns are a comfortable row on a monitor and three rows on a phone,
 * which push the actual clothes below the fold on the screen whose whole job
 * is showing them. So on a phone they collapse behind one button that says how
 * many are on; from 640px up the toggle does not exist and they are simply
 * there. The open state starts at "open" when something is already filtering,
 * because the first thing you want then is to see what.
 */
export default function FilterBar({ search, children, active = 0, extra }: Props) {
  const [open, setOpen] = useState(active > 0);

  return (
    <div className={`filterbar${open ? " open" : ""}`}>
      {search}
      <button
        type="button"
        className={`chip filter-toggle${active > 0 ? " active" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Filters verbergen" : active > 0 ? `Filters · ${active}` : "Filters"}
      </button>
      <div className="filterbar-fields">{children}</div>
      {extra}
    </div>
  );
}
