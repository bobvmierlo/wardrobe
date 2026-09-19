import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Preferences } from "./types";

const THEME_KEY = "kledingkast_theme";
export const DEFAULT_THEME = "midnight";

interface ThemeState {
  /** The palette in force. Never null — there is always a theme. */
  theme: string;
  /** Everything else this person chose, once it has been fetched. */
  preferences: Preferences | null;
  loading: boolean;
  setTheme: (theme: string) => Promise<void>;
  /** Save any subset of the preferences and keep the app in step with them. */
  save: (changes: Partial<Preferences>) => Promise<Preferences>;
  refresh: () => Promise<void>;
}

const ThemeContext = createContext<ThemeState | undefined>(undefined);

/** Remember the palette locally as well as on the server.
 *
 * Not because the server copy is unreliable, but because it arrives one round
 * trip after the first paint — and a light-theme user should not watch their
 * app flash dark on every cold start. The cached value paints immediately and
 * the fetched one corrects it if they differ. */
function cached(): string {
  try {
    return localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME; // private mode: the theme just does not persist
  }
}

function apply(theme: string) {
  document.documentElement.dataset.theme = theme || DEFAULT_THEME;
  try {
    localStorage.setItem(THEME_KEY, theme || DEFAULT_THEME);
  } catch {
    /* nothing to do: the theme is applied, it simply will not be remembered */
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [theme, setThemeState] = useState<string>(cached);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(true);

  // Paint the cached palette before anything is fetched.
  useEffect(() => {
    apply(theme);
  }, [theme]);

  const refresh = useCallback(async () => {
    if (!user) {
      setPreferences(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const prefs = await api.preferences();
      setPreferences(prefs);
      setThemeState(prefs.theme || DEFAULT_THEME);
    } catch {
      // Offline, or the server is down. The cached palette stays, and the
      // rest of the app has its own way of saying the connection is gone.
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = useCallback(async (changes: Partial<Preferences>) => {
    const saved = await api.savePreferences(changes);
    setPreferences(saved);
    setThemeState(saved.theme || DEFAULT_THEME);
    return saved;
  }, []);

  const setTheme = useCallback(
    async (next: string) => {
      // Applied first, saved second: picking a colour should feel instant,
      // and a failed save leaves the choice visible to try again.
      setThemeState(next);
      await save({ theme: next });
    },
    [save],
  );

  return (
    <ThemeContext.Provider value={{ theme, preferences, loading, setTheme, save, refresh }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme buiten ThemeProvider");
  return ctx;
}
