/**
 * How the API layer reads an answer — and, more importantly, a non-answer.
 *
 * One distinction in here is load-bearing: "the server said no" and "the server
 * said nothing" call for opposite reactions. A 401 means the session really is
 * over and the app should show the login screen; a failed connection means try
 * again later. Getting that backwards is what used to sign people out the first
 * time they opened the app on a train, and it is the reason OfflineError exists
 * as a separate type.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, getToken, setToken } from "./api";

/** A fetch that answers with this body and status, once. */
function answering(body: unknown, init: ResponseInit = {}) {
  return vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
      ...init,
    }),
  );
}

/** A fetch that never reaches the server, the way a dead connection behaves. */
function unreachable() {
  return vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  // The module redirects to /login on a real 401; jsdom cannot navigate, so
  // assign is stubbed and asserted on instead.
  vi.stubGlobal("location", { ...window.location, assign: vi.fn() });
});

describe("the token", () => {
  it("is absent until one is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("is kept and cleared", () => {
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it("rides along on every request once there is one", async () => {
    setToken("mijn-token");
    const fetchMock = answering({ id: 1 });
    vi.stubGlobal("fetch", fetchMock);
    await api.me();
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer mijn-token");
  });

  it("is simply left off when there is none", async () => {
    const fetchMock = answering({ self_registration: false });
    vi.stubGlobal("fetch", fetchMock);
    await api.authConfig();
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });
});

describe("a server that says no", () => {
  it("passes the server's own explanation through", async () => {
    vi.stubGlobal(
      "fetch",
      answering({ detail: "Deze gebruikersnaam bestaat al" }, { status: 409 }),
    );
    await expect(
      api.register({ username: "bob", display_name: "Bob", password: "lang-genoeg" }),
    ).rejects.toThrow("Deze gebruikersnaam bestaat al");
  });

  it("falls back to the status when there is no explanation", async () => {
    vi.stubGlobal("fetch", answering("<html>kapot</html>", { status: 500 }));
    await expect(api.me()).rejects.toThrow(/500/);
  });

  it("survives a detail that is not a plain string", async () => {
    // FastAPI's validation errors are a list of objects, not a sentence.
    vi.stubGlobal(
      "fetch",
      answering({ detail: [{ loc: ["body", "password"], msg: "too short" }] }, { status: 422 }),
    );
    await expect(api.me()).rejects.toThrow(/too short/);
  });

  it("ends the session on a 401 and sends the browser to the login screen", async () => {
    setToken("verlopen");
    vi.stubGlobal("fetch", answering({ detail: "Sessie verlopen" }, { status: 401 }));
    await expect(api.me()).rejects.toThrow();
    expect(getToken()).toBeNull();
    expect(location.assign).toHaveBeenCalledWith("/login");
  });

  it("does not redirect on a 401 from the login call itself", async () => {
    // There, a 401 is just the answer to "is this the right password?" — being
    // bounced to the login screen you are already on would lose the message.
    vi.stubGlobal("fetch", answering({ detail: "Onjuist" }, { status: 401 }));
    await expect(api.login("bob", "fout")).rejects.toThrow();
    expect(location.assign).not.toHaveBeenCalled();
  });

  it("shows the server's reason for a refused login, not 'sessie verlopen'", async () => {
    // This said "Sessie verlopen" for every 401, including a mistyped password,
    // which is both wrong and baffling to read. Caught by the end-to-end test.
    vi.stubGlobal(
      "fetch",
      answering({ detail: "Onjuiste gebruikersnaam of wachtwoord" }, { status: 401 }),
    );
    await expect(api.login("bob", "fout")).rejects.toThrow(
      "Onjuiste gebruikersnaam of wachtwoord",
    );
  });

  it("passes a throttling message through as the server wrote it", async () => {
    vi.stubGlobal(
      "fetch",
      answering(
        { detail: "Te veel mislukte inlogpogingen. Probeer het over 30 seconden opnieuw." },
        { status: 429 },
      ),
    );
    await expect(api.login("bob", "fout")).rejects.toThrow(/30 seconden/);
  });

  it("keeps the session when a *logged-in* call gets a 401", async () => {
    // The other half of the distinction: here the session really is over.
    setToken("verlopen");
    vi.stubGlobal("fetch", answering({ detail: "Niet ingelogd" }, { status: 401 }));
    await expect(api.listUsers()).rejects.toThrow("Sessie verlopen");
    expect(getToken()).toBeNull();
  });

  it("does not redirect on a 401 from an invitation lookup", async () => {
    vi.stubGlobal("fetch", answering({ detail: "nee" }, { status: 401 }));
    await expect(api.invitationInfo("een-token")).rejects.toThrow();
    expect(location.assign).not.toHaveBeenCalled();
  });
});

describe("a server that says nothing", () => {
  it("is not mistaken for a rejected session", async () => {
    setToken("nog-geldig");
    vi.stubGlobal("fetch", unreachable());
    await expect(api.me()).rejects.toThrow(/verbinding/i);
    // The one that matters: the token survives, so the train journey does not
    // cost you your login.
    expect(getToken()).toBe("nog-geldig");
    expect(location.assign).not.toHaveBeenCalled();
  });

  it("reports itself as offline so the bar can appear", async () => {
    vi.stubGlobal("fetch", unreachable());
    await expect(api.me()).rejects.toThrow();
    const { probeConnection } = await import("./online");
    vi.stubGlobal("fetch", unreachable());
    await expect(probeConnection()).resolves.toBe(false);
  });
});

describe("answers with no body", () => {
  it("treats a 204 as success rather than trying to read JSON", async () => {
    setToken("t");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.logout()).resolves.toBeUndefined();
  });
});

describe("the SSO login URL", () => {
  it("always names where to go afterwards", () => {
    expect(api.oidcLoginUrl()).toBe("/api/auth/oidc/login?next=%2F");
  });

  it("carries an invitation token when there is one", () => {
    const url = api.oidcLoginUrl({ invite: "abc123", next: "/outfits" });
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("invite")).toBe("abc123");
    expect(params.get("next")).toBe("/outfits");
  });

  it("escapes a token that would otherwise break the query string", () => {
    const url = api.oidcLoginUrl({ invite: "a&b=c d" });
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("invite")).toBe("a&b=c d");
  });
});
