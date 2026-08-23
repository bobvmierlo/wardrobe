import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { User } from "./types";

/** Runtime cache the service worker keeps photos in (see vite.config.ts). */
const PHOTO_CACHE = "wardrobe-photos";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadMe() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMe();
  }, []);

  async function login(username: string, password: string) {
    const res = await api.login(username, password);
    setToken(res.access_token);
    setUser(res.user);
  }

  function logout() {
    // Best-effort: the local token is what actually gates the app, so a
    // failed request here must not leave the user stuck on a logged-in screen.
    api.logout().catch(() => {});
    // The service worker holds this user's photos; the next person to log in
    // on this browser should not inherit them.
    globalThis.caches?.delete(PHOTO_CACHE).catch(() => {});
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth buiten AuthProvider");
  return ctx;
}
