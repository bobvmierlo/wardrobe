import { reportOffline } from "./online";
import type {
  AuditPage,
  AuthConfig,
  BackupPreview,
  Category,
  ColorLogic,
  ColorRule,
  Invitation,
  InvitationInfo,
  Item,
  JudgedPair,
  LogEntry,
  MemberRole,
  OutfitPartner,
  OutfitSuggestion,
  Pair,
  RejectedPartner,
  RestoreResult,
  RestoreTarget,
  ScrapeResult,
  SizeOption,
  Stats,
  User,
  Verdict,
  Wardrobe,
  WardrobeMember,
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

/** The request never reached the server — no connection, or it is down.
 *
 * Kept apart from :class:`ApiError` on purpose. "The server says no" and "the
 * server said nothing" call for opposite reactions: a 401 means the session is
 * really gone, while a failed connection means try again later — and used to
 * cost people their login the first time they opened the app on the train.
 */
class OfflineError extends Error {
  constructor(message = "Geen verbinding met de server") {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    // fetch only rejects when the request never completed: offline, DNS
    // failure, the server refusing the connection. Never a status code.
    reportOffline();
    throw new OfflineError();
  }
  if (res.status === 401) {
    setToken(null);
    // Force a re-login on session expiry — except on the endpoints that are
    // reachable while logged out, where a 401 is just an answer.
    if (!path.endsWith("/auth/login") && !path.startsWith("/api/invitations/")) {
      window.location.assign("/login");
    }
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


/** Download a file the API guards with a bearer token.
 *
 * A plain link cannot carry the Authorization header, so the response is
 * fetched, turned into a blob and handed to a throwaway <a download>. The
 * filename comes from Content-Disposition, which is what the server chose.
 */
async function download(path: string, fallbackName: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(path, { headers });
  } catch {
    reportOffline();
    throw new OfflineError("Downloaden lukt niet zonder verbinding");
  }
  if (!res.ok) {
    let detail = `Downloaden mislukt (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* a non-JSON error body tells us nothing extra */
    }
    throw new ApiError(res.status, detail);
  }

  const disposition = res.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking immediately can cut the download short in Safari.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
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
  // Drops the server-side photo cookie; the bearer token is cleared locally.
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  changePassword: (new_password: string) =>
    request<void>("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password }),
    }),

  // ---- the front door (readable while logged out) ----
  authConfig: () => request<AuthConfig>("/api/auth/config"),
  setSelfRegistration: (self_registration: boolean) =>
    request<AuthConfig>("/api/auth/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ self_registration }),
    }),
  register: (data: { username: string; display_name: string; password: string }) =>
    request<{ access_token: string; user: User }>("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // ---- users ----
  listUsers: () => request<User[]>("/api/users"),
  createUser: (data: { username: string; display_name: string; password: string; is_admin: boolean }) =>
    request<User>("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateUser: (id: number, data: { is_admin: boolean }) =>
    request<User>(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),

  // ---- wardrobes (kasten) & sharing ----
  listWardrobes: () => request<Wardrobe[]>("/api/wardrobes"),
  wardrobeMembers: (wardrobeId: number) =>
    request<WardrobeMember[]>(`/api/wardrobes/${wardrobeId}/members`),
  inviteMember: (wardrobeId: number, username: string, role: MemberRole) =>
    request<WardrobeMember>(`/api/wardrobes/${wardrobeId}/members`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, role }),
    }),
  updateMember: (wardrobeId: number, userId: number, role: MemberRole) =>
    request<WardrobeMember>(`/api/wardrobes/${wardrobeId}/members/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),
  removeMember: (wardrobeId: number, userId: number) =>
    request<void>(`/api/wardrobes/${wardrobeId}/members/${userId}`, { method: "DELETE" }),

  // ---- invitation links ----
  listInvitations: (wardrobeId: number) =>
    request<Invitation[]>(`/api/wardrobes/${wardrobeId}/invitations`),
  createInvitation: (
    wardrobeId: number,
    data: { role: MemberRole; label?: string | null; expires_days?: number | null },
  ) =>
    request<Invitation>(`/api/wardrobes/${wardrobeId}/invitations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  // Account links (beheerder): a login for someone new, no kast shared.
  listAccountInvitations: () => request<Invitation[]>("/api/invitations/account"),
  createAccountInvitation: (data: { label?: string | null; expires_days?: number | null }) =>
    request<Invitation>("/api/invitations/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  revokeInvitation: (invitationId: number) =>
    request<void>(`/api/invitations/${invitationId}`, { method: "DELETE" }),
  // Reachable without a login: the token is the credential.
  invitationInfo: (token: string) => request<InvitationInfo>(`/api/invitations/${token}`),
  acceptInvitation: (token: string) =>
    request<void>(`/api/invitations/${token}/accept`, { method: "POST" }),
  registerViaInvitation: (
    token: string,
    data: { username: string; display_name: string; password: string },
  ) =>
    request<{ access_token: string; user: User }>(`/api/invitations/${token}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // ---- audit trail & application log (beheerder) ----
  auditTrail: (
    params: { action?: string; user_id?: number; wardrobe_id?: number; q?: string; limit?: number; offset?: number } = {},
  ) => {
    const sp = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
    });
    const query = sp.toString();
    return request<AuditPage>(`/api/audit${query ? `?${query}` : ""}`);
  },
  appLogs: (params: { level?: string; limit?: number } = {}) => {
    const sp = new URLSearchParams();
    if (params.level) sp.set("level", params.level);
    if (params.limit) sp.set("limit", String(params.limit));
    const query = sp.toString();
    return request<LogEntry[]>(`/api/logs${query ? `?${query}` : ""}`);
  },

  // ---- colour-combination rules (editable suggestion logic) ----
  colorLogic: () => request<ColorLogic>("/api/color-rules"),
  addColorRule: (data: { color_a: string; color_b: string; verdict: "good" | "bad" }) =>
    request<ColorRule>("/api/color-rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteColorRule: (id: number) => request<void>(`/api/color-rules/${id}`, { method: "DELETE" }),

  // ---- items ----
  listItems: (
    wardrobeId: number,
    params: { category?: string; q?: string; favorites?: boolean } = {},
  ) => {
    const sp = new URLSearchParams();
    sp.set("wardrobe_id", String(wardrobeId));
    if (params.category) sp.set("category", params.category);
    if (params.q) sp.set("q", params.q);
    if (params.favorites) sp.set("favorites", "true");
    return request<Item[]>(`/api/items?${sp.toString()}`);
  },
  getItem: (id: number) => request<Item>(`/api/items/${id}`),
  // Brands already in use, for the item form's brand picker. Free text on
  // items, so any user can introduce a new one — no admin needed.
  listBrands: () => request<string[]>("/api/brands"),
  createItem: (wardrobeId: number, form: FormData) => {
    form.set("wardrobe_id", String(wardrobeId));
    return request<Item>("/api/items", { method: "POST", body: form });
  },
  updateItem: (id: number, form: FormData) =>
    request<Item>(`/api/items/${id}`, { method: "PATCH", body: form }),
  duplicateItem: (id: number) => request<Item>(`/api/items/${id}/duplicate`, { method: "POST" }),
  deleteItem: (id: number) => request<void>(`/api/items/${id}`, { method: "DELETE" }),

  // ---- matches ----
  nextPair: (wardrobeId: number, anchorId?: number) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    if (anchorId) sp.set("anchor_id", String(anchorId));
    return request<Pair | null>(`/api/matches/next?${sp.toString()}`);
  },
  submitVerdict: (item_a_id: number, item_b_id: number, verdict: Verdict) =>
    request<void>("/api/matches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_a_id, item_b_id, verdict }),
    }),
  // Postpone a pair: no verdict, it returns at the end of the queue.
  skipPair: (item_a_id: number, item_b_id: number) =>
    request<void>("/api/matches/skip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_a_id, item_b_id }),
    }),
  resetPair: (a: number, b: number) =>
    request<void>(`/api/matches/${a}/${b}`, { method: "DELETE" }),
  judgedPairs: (wardrobeId: number, verdict?: Verdict) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    if (verdict) sp.set("verdict", verdict);
    return request<JudgedPair[]>(`/api/matches/judged?${sp.toString()}`);
  },
  acceptSuggestion: (item_ids: number[]) =>
    request<void>("/api/matches/suggestions/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids }),
    }),
  // Undo a whole adopted outfit in one request, rather than one per pair.
  undoSuggestion: (item_ids: number[]) =>
    request<void>("/api/matches/suggestions/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids }),
    }),
  outfitsFor: (itemId: number) => request<OutfitPartner[]>(`/api/matches/outfits/${itemId}`),
  // Pairs that were judged not to work, for the garment's own page.
  rejectedFor: (itemId: number) => request<RejectedPartner[]>(`/api/matches/rejected/${itemId}`),
  suggestions: (wardrobeId: number) =>
    request<OutfitSuggestion[]>(`/api/matches/suggestions?wardrobe_id=${wardrobeId}`),
  suggestionsFor: (itemId: number) =>
    request<OutfitSuggestion[]>(`/api/matches/suggestions/${itemId}`),
  pairQueue: (wardrobeId: number, anchorId?: number, limit = 25) =>
    request<Pair[]>(
      `/api/matches/next/queue?wardrobe_id=${wardrobeId}&limit=${limit}` +
        (anchorId != null ? `&anchor_id=${anchorId}` : "")
    ),
  stats: (wardrobeId: number) =>
    request<Stats>(`/api/matches/stats?wardrobe_id=${wardrobeId}`),

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

  // ---- back-up, export and restore ----
  exportWardrobe: (wardrobeId: number) =>
    download(`/api/backup/wardrobe/${wardrobeId}`, "kledingkast-export.zip"),
  exportEverything: () => download("/api/backup/instance", "kledingkast-volledig.zip"),
  exportSnapshot: () => download("/api/backup/snapshot", "kledingkast-momentopname.zip"),
  restoreTargets: () => request<RestoreTarget[]>("/api/backup/wardrobes"),
  inspectBackup: (file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request<BackupPreview>("/api/backup/inspect", { method: "POST", body });
  },
  restoreBackup: (file: File, wardrobeId: number, mode: "merge" | "replace") => {
    const body = new FormData();
    body.set("file", file);
    body.set("wardrobe_id", String(wardrobeId));
    body.set("mode", mode);
    return request<RestoreResult>("/api/backup/restore", { method: "POST", body });
  },

  // ---- app version (from backend/app/_version.py) ----
  version: () => request<{ version: string }>("/api/version"),
};

export function photoUrl(item: Item, thumb = false): string | null {
  const name = thumb ? item.thumb_filename : item.photo_filename;
  return name ? `/uploads/${name}` : null;
}

export { ApiError, OfflineError };
