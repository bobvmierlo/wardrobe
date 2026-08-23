import { useEffect, useState } from "react";

/** Whether the app currently has a working connection.
 *
 * Harder than it sounds. `navigator.onLine` is not reliable on its own: it
 * only knows whether the device has *a* network, it can still read `true`
 * behind a captive portal, and — the one that actually bit us — a document
 * restored from the service worker cache can start life reporting `true` and
 * only correct itself a moment later, with no event to announce it.
 *
 * Nor can ordinary requests be trusted as a signal any more: the GETs that
 * render a screen are answered from cache when the network is gone, so they
 * succeed either way.
 *
 * So the truth is established by asking the server something small that is
 * deliberately never cached, and by listening for the browser's own events in
 * between. A request that dies outright still counts as proof of offline.
 */

/** Deliberately outside the runtime caches, so it always hits the network. */
const PROBE_URL = "/api/version";

let offline = false;
const listeners = new Set<(online: boolean) => void>();

function set(next: boolean) {
  if (offline === !next) return;
  offline = !next;
  for (const listener of listeners) listener(next);
}

/** Called from the API layer when a request never reached the server. */
export function reportOffline() {
  set(false);
}

/** Ask the server whether it is there. Never throws. */
export async function probeConnection(): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    set(false);
    return false;
  }
  try {
    await fetch(PROBE_URL, { cache: "no-store" });
    set(true);
    return true;
  } catch {
    set(false);
    return false;
  }
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(!offline);

  useEffect(() => {
    listeners.add(setOnline);
    // The value we started with may already be wrong — check for real.
    probeConnection();

    const goOnline = () => {
      probeConnection();
    };
    const goOffline = () => set(false);
    const onVisible = () => {
      if (document.visibilityState === "visible") probeConnection();
    };

    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      listeners.delete(setOnline);
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return online;
}
