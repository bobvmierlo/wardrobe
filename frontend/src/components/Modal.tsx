import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Buttons along the bottom. Stays put while the body scrolls. */
  footer?: ReactNode;
  /** Wider panel, for a dialog full of photos rather than a form. */
  wide?: boolean;
}

/** A dialog that opens where you are looking.
 *
 * Written for the one complaint that has no workaround: a form rendered at the
 * top of a long page, opened by a button three hundred looks further down.
 * Nothing appears to happen, because what appeared is off-screen. A dialog
 * cannot have that problem — it is positioned against the window, not against
 * the document — and it takes the scroll position with it when it closes,
 * which a "scroll to top" fix deliberately does not.
 *
 * Rendered through a portal so the backdrop is never trapped inside a parent
 * with `overflow: hidden` or a stacking context of its own.
 */
export default function Modal({ title, onClose, children, footer, wide }: Props) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // The page behind must not scroll along: on a phone that is how you end
    // up having scrolled the list instead of the dialog.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Move focus in, so a keyboard lands inside the dialog rather than on
    // whatever was focused behind it.
    panel.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return createPortal(
    <div
      className="modal-backdrop"
      // Only a click on the backdrop itself closes: a drag that starts inside
      // the panel and ends outside it is not a request to throw the form away.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`modal-panel${wide ? " wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panel}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Sluiten">
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
