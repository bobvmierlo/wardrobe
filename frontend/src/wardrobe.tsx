import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Wardrobe } from "./types";

const CURRENT_KEY = "kledingkast_wardrobe";

interface WardrobeState {
  wardrobes: Wardrobe[];
  current: Wardrobe | null;
  loading: boolean;
  /** True when the active wardrobe belongs to someone else. */
  isShared: boolean;
  /** Whether the user may add/edit garments in the active wardrobe. */
  canEdit: boolean;
  select: (id: number) => void;
  refresh: () => Promise<void>;
}

const WardrobeContext = createContext<WardrobeState | undefined>(undefined);

export function WardrobeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [wardrobes, setWardrobes] = useState<Wardrobe[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(() => {
    const raw = localStorage.getItem(CURRENT_KEY);
    return raw ? Number(raw) : null;
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) {
      setWardrobes([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const list = await api.listWardrobes();
      setWardrobes(list);
      // Keep the stored selection if it's still reachable, else fall back to
      // the user's own kast (always the first entry the API returns).
      setCurrentId((cur) => {
        if (cur && list.some((w) => w.id === cur)) return cur;
        return list.length ? list[0].id : null;
      });
    } catch {
      setWardrobes([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const select = useCallback((id: number) => {
    setCurrentId(id);
    localStorage.setItem(CURRENT_KEY, String(id));
  }, []);

  useEffect(() => {
    if (currentId != null) localStorage.setItem(CURRENT_KEY, String(currentId));
  }, [currentId]);

  const current = wardrobes.find((w) => w.id === currentId) ?? null;

  const value: WardrobeState = {
    wardrobes,
    current,
    loading,
    isShared: !!current && current.my_role !== "owner",
    canEdit: !!current && current.can_edit,
    select,
    refresh,
  };

  return <WardrobeContext.Provider value={value}>{children}</WardrobeContext.Provider>;
}

export function useWardrobe(): WardrobeState {
  const ctx = useContext(WardrobeContext);
  if (!ctx) throw new Error("useWardrobe buiten WardrobeProvider");
  return ctx;
}
