import type {
  Category,
  Item,
  OutfitPartner,
  OutfitSuggestion,
  Pair,
  ScrapeResult,
  SizeOption,
  Stats,
  User,
} from "./types";

const TOKEN_KEY = "kledingkast_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    setToken(null);
    // Force a re-login on session expiry.
    if (!path.endsWith("/auth/login")) window.location.assign("/login");
    throw new ApiError(401, "Sessie verlopen");
  }
  if (!res.ok) {
    let detail = `Er ging iets mis (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // ---- auth ----
  async login(username: string, password: string): Promise<{ access_token: string; user: User }> {
    const form = new URLSearchParams();
    form.set("username", username);
    form.set("password", password);
    return request("/api/auth/login", { method: "POST", body: form });
  },
  me: () => request<User>("/api/auth/me"),
  changePassword: (new_password: string) =>
    request<void>("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password }),
    }),

  // ---- users ----
  listUsers: () => request<User[]>("/api/users"),
  createUser: (data: { username: string; display_name: string; password: string; is_admin: boolean }) =>
    request<User>("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),

  // ---- items ----
  listItems: (params: { category?: string; q?: string; favorites?: boolean } = {}) => {
    const sp = new URLSearchParams();
    if (params.category) sp.set("category", params.category);
    if (params.q) sp.set("q", params.q);
    if (params.favorites) sp.set("favorites", "true");
    const qs = sp.toString();
    return request<Item[]>(`/api/items${qs ? `?${qs}` : ""}`);
  },
  getItem: (id: number) => request<Item>(`/api/items/${id}`),
  createItem: (form: FormData) => request<Item>("/api/items", { method: "POST", body: form }),
  updateItem: (id: number, form: FormData) =>
    request<Item>(`/api/items/${id}`, { method: "PATCH", body: form }),
  deleteItem: (id: number) => request<void>(`/api/items/${id}`, { method: "DELETE" }),

  // ---- matches ----
  nextPair: (anchorId?: number) =>
    request<Pair | null>(`/api/matches/next${anchorId ? `?anchor_id=${anchorId}` : ""}`),
  submitVerdict: (item_a_id: number, item_b_id: number, verdict: "yes" | "no") =>
    request<void>("/api/matches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_a_id, item_b_id, verdict }),
    }),
  resetPair: (a: number, b: number) =>
    request<void>(`/api/matches/${a}/${b}`, { method: "DELETE" }),
  outfitsFor: (itemId: number) => request<OutfitPartner[]>(`/api/matches/outfits/${itemId}`),
  suggestions: () => request<OutfitSuggestion[]>("/api/matches/suggestions"),
  stats: () => request<Stats>("/api/matches/stats"),

  // ---- categories (admin-managed) ----
  listCategories: () => request<Category[]>("/api/categories"),
  createCategory: (name: string) =>
    request<Category>("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  deleteCategory: (id: number) => request<void>(`/api/categories/${id}`, { method: "DELETE" }),

  // ---- sizes (admin-managed) ----
  listSizes: () => request<SizeOption[]>("/api/sizes"),
  createSize: (label: string, kind: SizeOption["kind"] = "clothing") =>
    request<SizeOption>("/api/sizes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, kind }),
    }),
  deleteSize: (id: number, force = false) =>
    request<void>(`/api/sizes/${id}${force ? "?force=true" : ""}`, { method: "DELETE" }),

  // ---- webshop import ----
  scrape: (url: string) => request<ScrapeResult>(`/api/import/scrape?url=${encodeURIComponent(url)}`),
};

export function photoUrl(item: Item, thumb = false): string | null {
  const name = thumb ? item.thumb_filename : item.photo_filename;
  return name ? `/uploads/${name}` : null;
}

export { ApiError };
