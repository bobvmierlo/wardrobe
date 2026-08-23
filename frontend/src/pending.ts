import type { Verdict } from "./types";

/** A verdict handed to the service worker while there was no connection.
 *
 * The service worker will replay the request — that part is out of our hands
 * and works even with the app closed. What this list is for is the *screen*:
 * knowing how many decisions are still in flight, and not offering the same
 * pair again before the server has heard about it.
 */
export interface PendingVerdict {
  a: number;
  b: number;
  /** "skip" is a postponement rather than a verdict, but queues the same way. */
  verdict: Verdict | "skip";
}

const KEY = "kledingkast_pending";

/** Two garments, in the order the server stores them. */
export function pairKey(a: number, b: number): string {
  return a < b ? `${a}-${b}` : `${b}-${a}`;
}

function read(): Record<string, PendingVerdict[]> {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Record<string, PendingVerdict[]>) : {};
  } catch {
    return {};
  }
}

function write(all: Record<string, PendingVerdict[]>) {
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* private mode: the service worker still replays, we just cannot count */
  }
}

export function listPending(wardrobeId: number): PendingVerdict[] {
  return read()[String(wardrobeId)] ?? [];
}

/** Remember a queued decision. The newest verdict on a pair wins. */
export function addPending(wardrobeId: number, entry: PendingVerdict): PendingVerdict[] {
  const all = read();
  const id = String(wardrobeId);
  const rest = (all[id] ?? []).filter((p) => pairKey(p.a, p.b) !== pairKey(entry.a, entry.b));
  all[id] = [...rest, entry];
  write(all);
  return all[id];
}

/** Drop everything the server has evidently received. */
export function settlePending(wardrobeId: number, landed: Set<string>): PendingVerdict[] {
  const all = read();
  const id = String(wardrobeId);
  all[id] = (all[id] ?? []).filter((p) => !landed.has(pairKey(p.a, p.b)));
  write(all);
  return all[id];
}
