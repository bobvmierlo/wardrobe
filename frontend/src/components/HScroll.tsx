import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  /** Classes for the scrolling track itself (e.g. "chips", "pick-strip"). */
  className?: string;
  children: ReactNode;
  /** Accessible name — a scrollable strip is a landmark of its own. */
  label?: string;
  /** Set false for strips where the paging buttons would only be in the way. */
  arrows?: boolean;
}

/** A horizontal strip that scrolls without the browser's grey scrollbar.
 *
 * The scrollbar is replaced by two cues that only show up when they mean
 * something: the content fades out on whichever side has more to see, and on
 * mouse-and-keyboard devices a pair of paging buttons appears on hover. Touch
 * users just swipe, and get the fades.
 */
export default function HScroll({ className = "", children, label, arrows = true }: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  // Which sides still have content beyond the edge — drives both the fades
  // and whether a paging button is worth showing at all.
  const [more, setMore] = useState({ start: false, end: false });

  const sync = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    // Sub-pixel layout means scrollLeft rarely hits the exact maximum, so
    // allow a pixel of slack before claiming there is more to scroll.
    const max = el.scrollWidth - el.clientWidth;
    const next = { start: el.scrollLeft > 1, end: el.scrollLeft < max - 1 };
    setMore((prev) => (prev.start === next.start && prev.end === next.end ? prev : next));
  }, []);

  // Re-measure after every render: the item list, the filters and the window
  // can all change the strip's width without a scroll event ever firing.
  useEffect(sync);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver(sync);
    observer.observe(el);
    for (const child of Array.from(el.children)) observer.observe(child);
    return () => observer.disconnect();
  }, [sync]);

  function page(direction: -1 | 1) {
    const el = trackRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: "smooth" });
  }

  const fades = `${more.start ? " fade-start" : ""}${more.end ? " fade-end" : ""}`;

  return (
    <div className="hscroll">
      <div
        ref={trackRef}
        className={`hscroll-track ${className}${fades}`}
        onScroll={sync}
        role={label ? "group" : undefined}
        aria-label={label}
      >
        {children}
      </div>
      {arrows && more.start && (
        <button type="button" className="hscroll-arrow start" onClick={() => page(-1)} aria-label="Naar links" tabIndex={-1}>
          ‹
        </button>
      )}
      {arrows && more.end && (
        <button type="button" className="hscroll-arrow end" onClick={() => page(1)} aria-label="Naar rechts" tabIndex={-1}>
          ›
        </button>
      )}
    </div>
  );
}
