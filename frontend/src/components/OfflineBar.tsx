import { useAuth } from "../auth";
import { useOnline } from "../online";

/** A standing reminder that what you see may be out of date.
 *
 * An installed app hides the browser's own offline page, so without this the
 * app looks like it is simply telling you the truth while quietly serving
 * whatever it cached last. In a shared kast that matters: your partner may
 * have judged half a wardrobe since.
 */
export default function OfflineBar({ pending = 0 }: { pending?: number }) {
  const online = useOnline();
  const { stale } = useAuth();
  if (online) return null;

  return (
    <div className="offline-bar" role="status">
      <span aria-hidden="true">☁️</span>
      <span>
        <strong>Geen verbinding.</strong>{" "}
        {stale
          ? "Je ziet je kast zoals die het laatst geladen was."
          : "Wijzigingen van anderen zie je pas als je weer online bent."}
        {pending > 0 && (
          <>
            {" "}
            {pending} {pending === 1 ? "oordeel wacht" : "oordelen wachten"} op verbinding.
          </>
        )}
      </span>
    </div>
  );
}
