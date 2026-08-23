import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, OfflineError, setToken } from "./api";
import type { User } from "./types";

/** Caches the service worker keeps per signed-in person (see vite.config.ts).
 *  Both are wiped when the person at the keyboard changes. */
const CACHES = ["wardrobe-photos", "wardrobe-api"];

/** The last person known to be signed in here.
 *
 * Without this an offline start has nothing to show: the token is in hand but
 * the server cannot confirm who it belongs to, and the app would have to
 * assume the worst and show a login form it cannot submit.
 */
const USER_KEY = "kledingkast_user";

interface AuthState {
  user: User | null;
  loading: boolean;
  /** True when we are running on a remembered user rather than a fresh check. */
  stale: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

function rememberedUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

function remember(user: User | null) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  } catch {
    /* private mode: the app still works, it just cannot start offline */
  }
}

/** Drop everything cached for the person who was signed in here. */
function clearCaches() {
  for (const name of CACHES) globalThis.caches?.delete(name).catch(() => {});
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);

  async function loadMe() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      remember(me);
      setUser(me);
      setStale(false);
    } catch (e) {
      if (e instanceof OfflineError) {
        // The server said nothing, so it did not say "no". Keep the session
        // and carry on with the person we last saw — the whole point of an
        // installed app is that it opens when the network does not.
        setUser(rememberedUser());
        setStale(true);
      } else {
        // A real rejection (401): the session is over.
        setToken(null);
        remember(null);
        clearCaches();
        setUser(null);
        setStale(false);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMe();
  }, []);

  // A connection that comes back is the moment to find out whether the session
  // we kept is still any good.
  useEffect(() => {
    const recheck = () => {
      if (getToken()) loadMe();
    };
    window.addEventListener("online", recheck);
    return () => window.removeEventListener("online", recheck);
  }, []);

  async function login(username: string, password: string) {
    // Whoever was here before, their cached kast is not this person's to see.
    clearCaches();
    const res = await api.login(username, password);
    setToken(res.access_token);
    remember(res.user);
    setUser(res.user);
    setStale(false);
  }

  function logout() {
    // Best-effort: the local token is what actually gates the app, so a
    // failed request here must not leave the user stuck on a logged-in screen.
    api.logout().catch(() => {});
    // The service worker holds this user's photos and data; the next person to
    // log in on this browser should not inherit them.
    clearCaches();
    setToken(null);
    remember(null);
    setUser(null);
    setStale(false);
  }

  return (
    <AuthContext.Provider value={{ user, loading, stale, login, logout, refresh: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth buiten AuthProvider");
  return ctx;
}
