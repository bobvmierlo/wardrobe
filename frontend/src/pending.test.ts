/**
 * The queue of verdicts given while there was no connection.
 *
 * This is the bookkeeping the *screen* relies on: how many decisions are still
 * in flight, and which pairs must not be offered again before the server has
 * heard about them. The service worker does the actual replaying, so a mistake
 * here does not lose a verdict — it shows someone the same pair twice, or
 * silently drops one from the count, which is the kind of bug you only notice
 * as "the app is behaving oddly".
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { addPending, listPending, pairKey, settlePending } from "./pending";

beforeEach(() => {
  localStorage.clear();
});

describe("pairKey", () => {
  it("names a pair the same way round whichever order it is given", () => {
    // The server stores the lower id first; the queue has to agree or the same
    // pair would be tracked as two.
    expect(pairKey(3, 7)).toBe(pairKey(7, 3));
    expect(pairKey(3, 7)).toBe("3-7");
  });

  it("does not confuse pairs that share a digit", () => {
    expect(pairKey(1, 12)).not.toBe(pairKey(11, 2));
  });
});

describe("the queue", () => {
  it("starts empty and stays empty for a kast nobody has touched", () => {
    expect(listPending(1)).toEqual([]);
  });

  it("keeps a verdict and hands it back", () => {
    addPending(1, { a: 2, b: 5, verdict: "yes" });
    expect(listPending(1)).toEqual([{ a: 2, b: 5, verdict: "yes" }]);
  });

  it("keeps each kast's queue to itself", () => {
    addPending(1, { a: 2, b: 5, verdict: "yes" });
    addPending(2, { a: 9, b: 9, verdict: "no" });
    expect(listPending(1)).toHaveLength(1);
    expect(listPending(2)).toHaveLength(1);
    expect(listPending(3)).toEqual([]);
  });

  it("lets the newest verdict on a pair win instead of queueing both", () => {
    addPending(1, { a: 2, b: 5, verdict: "yes" });
    const after = addPending(1, { a: 2, b: 5, verdict: "no" });
    expect(after).toEqual([{ a: 2, b: 5, verdict: "no" }]);
  });

  it("treats a pair given the other way round as the same pair", () => {
    addPending(1, { a: 2, b: 5, verdict: "yes" });
    const after = addPending(1, { a: 5, b: 2, verdict: "no" });
    expect(after).toHaveLength(1);
    expect(after[0].verdict).toBe("no");
  });

  it("queues a postponement alongside real verdicts", () => {
    addPending(1, { a: 2, b: 5, verdict: "yes" });
    addPending(1, { a: 3, b: 6, verdict: "skip" });
    expect(listPending(1).map((p) => p.verdict)).toEqual(["yes", "skip"]);
  });

  it("keeps the order decisions were made in", () => {
    addPending(1, { a: 1, b: 2, verdict: "yes" });
    addPending(1, { a: 3, b: 4, verdict: "no" });
    addPending(1, { a: 5, b: 6, verdict: "skip" });
    expect(listPending(1).map((p) => p.a)).toEqual([1, 3, 5]);
  });

  it("moves a re-judged pair to the back, because that is when it was decided", () => {
    addPending(1, { a: 1, b: 2, verdict: "yes" });
    addPending(1, { a: 3, b: 4, verdict: "no" });
    addPending(1, { a: 1, b: 2, verdict: "no" });
    expect(listPending(1).map((p) => p.a)).toEqual([3, 1]);
  });
});

describe("settling what the server has received", () => {
  it("drops the pairs that landed and keeps the rest", () => {
    addPending(1, { a: 1, b: 2, verdict: "yes" });
    addPending(1, { a: 3, b: 4, verdict: "no" });
    const left = settlePending(1, new Set([pairKey(1, 2)]));
    expect(left).toEqual([{ a: 3, b: 4, verdict: "no" }]);
    expect(listPending(1)).toEqual([{ a: 3, b: 4, verdict: "no" }]);
  });

  it("recognises a landed pair given in either order", () => {
    addPending(1, { a: 5, b: 2, verdict: "yes" });
    expect(settlePending(1, new Set(["2-5"]))).toEqual([]);
  });

  it("settling nothing changes nothing", () => {
    addPending(1, { a: 1, b: 2, verdict: "yes" });
    expect(settlePending(1, new Set())).toHaveLength(1);
  });

  it("settling an empty queue is harmless", () => {
    expect(settlePending(99, new Set(["1-2"]))).toEqual([]);
  });

  it("leaves another kast's queue alone", () => {
    addPending(1, { a: 1, b: 2, verdict: "yes" });
    addPending(2, { a: 1, b: 2, verdict: "yes" });
    settlePending(1, new Set([pairKey(1, 2)]));
    expect(listPending(2)).toHaveLength(1);
  });
});

describe("when localStorage will not cooperate", () => {
  /**
   * Private browsing, blocked site data, a full quota. The service worker still
   * replays the verdicts, so the app has to keep working — it just cannot
   * count. Throwing here would take the swipe screen down with it.
   */
  it("reads as empty rather than throwing", () => {
    const broken = () => {
      throw new Error("SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(broken);
    expect(listPending(1)).toEqual([]);
  });

  it("survives a write it cannot make", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => addPending(1, { a: 1, b: 2, verdict: "yes" })).not.toThrow();
  });

  it("reads as empty when the stored value is not JSON", () => {
    localStorage.setItem("kledingkast_pending", "{niet json");
    expect(listPending(1)).toEqual([]);
  });
});
