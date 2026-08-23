import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface ConfirmOptions {
  /** One line, phrased as the question being answered. */
  title: string;
  /** Optional detail: what exactly disappears, what stays. Newlines survive. */
  body?: string;
  /** Label on the confirming button. Defaults to "Verwijderen". */
  confirmLabel?: string;
  cancelLabel?: string;
  /** Paint the confirming button as destructive. On by default. */
  danger?: boolean;
}

type Ask = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Ask | undefined>(undefined);

interface Pending extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

/** An in-app replacement for window.confirm().
 *
 * The native dialog is unstyled, looks wrong inside an installed PWA, and on
 * some iOS versions is suppressed entirely in standalone mode — which would
 * let a delete through unconfirmed. This one is just a component, so it is
 * always shown and always blocks on a real answer.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);

  const ask = useCallback<Ask>(
    (options) => new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    []
  );

  // Answering resolves the promise exactly once: settle first, then close.
  const answer = useCallback(
    (ok: boolean) => {
      setPending((p) => {
        p?.resolve(ok);
        return null;
      });
    },
    []
  );

  useEffect(() => {
    if (!pending) return;
    confirmButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") answer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, answer]);

  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {pending && (
        <div className="editor-backdrop" role="presentation" onClick={() => answer(false)}>
          <div
            className="confirm-panel"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-title" className="confirm-title">
              {pending.title}
            </h2>
            {pending.body && <p className="confirm-body">{pending.body}</p>}
            <div className="confirm-actions">
              <button type="button" className="btn-ghost" onClick={() => answer(false)}>
                {pending.cancelLabel ?? "Annuleren"}
              </button>
              <button
                type="button"
                ref={confirmButton}
                className={pending.danger === false ? "btn-primary" : "btn-danger"}
                onClick={() => answer(true)}
              >
                {pending.confirmLabel ?? "Verwijderen"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): Ask {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm buiten ConfirmProvider");
  return ctx;
}
