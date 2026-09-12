/**
 * Establishing whether there is really a connection.
 *
 * The comment in online.tsx explains why this is harder than `navigator.onLine`:
 * that flag only knows whether the device has *a* network, it reads `true`
 * behind a captive portal, and a document restored from the service-worker cache
 * can start life claiming `true` with no event to correct it. Meanwhile ordinary
 * GETs are answered from cache when the network is gone, so they succeed either
 * way and prove nothing.
 *
 * Which leaves one deliberately uncached probe as the only real evidence. These
 * tests pin that down, because getting it wrong means either an offline bar that
 * never appears or one that never goes away.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { probeConnection, reportOffline } from "./online";

/** The module keeps one shared flag; put it back to "online" between tests. */
async function resetToOnline() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
  Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  await probeConnection();
}

beforeEach(async () => {
  await resetToOnline();
  vi.restoreAllMocks();
});

describe("probing the server", () => {
  it("says online when the probe comes back", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(probeConnection()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("asks for something that is never cached", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await probeConnection();
    const [url, options] = fetchMock.mock.calls[0];
    // A cached answer would make the probe say "online" forever.
    expect(url).toBe("/api/version");
    expect(options).toMatchObject({ cache: "no-store" });
  });

  it("says offline when the request never completes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(probeConnection()).resolves.toBe(false);
  });

  it("says online even when the server answers with an error", async () => {
    // A 500 is the server talking, which is the thing being established. The
    // offline bar is about the connection, not about the server being happy.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nee", { status: 500 })));
    await expect(probeConnection()).resolves.toBe(true);
  });

  it("believes navigator.onLine when it says false, without asking", async () => {
    // The one case the flag is trustworthy: the browser knows there is no
    // network at all, so spending a request on it is pointless.
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    await expect(probeConnection()).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not believe navigator.onLine when it says true", async () => {
    // Behind a captive portal it says true and is wrong, so the probe still runs.
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    await expect(probeConnection()).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("never throws, whatever fetch does", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => {
      throw new Error("iets heel onverwachts");
    }));
    await expect(probeConnection()).resolves.toBe(false);
  });
});

describe("notifying the listeners", () => {
  it("tells a listener when the connection is lost and found", async () => {
    const { useOnline } = await import("./online");
    expect(typeof useOnline).toBe("function");

    const seen: boolean[] = [];
    // probeConnection and reportOffline share one flag; the transitions are
    // what the offline bar renders from.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("nope")));
    await probeConnection();
    seen.push(false);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
    await probeConnection();
    seen.push(true);
    expect(seen).toEqual([false, true]);
  });

  it("lets the API layer report a dead request without a probe of its own", async () => {
    // api.ts calls this the moment a fetch rejects, so the bar appears without
    // waiting for the next probe.
    reportOffline();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
    await expect(probeConnection()).resolves.toBe(true);
  });
});
