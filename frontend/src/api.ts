import { reportOffline } from "./online";
import type {
  AuditPage,
  AuthConfig,
  AutofillLooksResult,
  AutofillPreview,
  AutofillTagsResult,
  BackupPreview,
  Category,
  DayPlan,
  Insights,
  ColorLogic,
  ColorRule,
  Invitation,
  InvitationInfo,
  Item,
  JudgedPair,
  LogEntry,
  MemberRole,
  Occasion,
  Outfit,
  OutfitDraft,
  OutfitPartner,
  OutfitSuggestion,
  Pair,
  Place,
  Preferences,
  RecommendationPage,
  RejectedPartner,
  RestoreResult,
  RestoreTarget,
  ScheduledBackup,
  ScheduledBackups,
  ScrapeResult,
  SizeOption,
  Stats,
  StyleGuide,
  StyleProfile,
  Trip,
  TripDetail,
  User,
  Verdict,
  Wardrobe,
  WardrobeMember,
  Weather,
  Week,
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

/** The server's explanation for a failure, or ``fallback`` when it gave none. */
async function detailFrom(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) {
      return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    /* a non-JSON error body tells us nothing extra */
  }
  return fallback;
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
    // On the endpoints reachable while logged out, a 401 is an *answer* — the
    // login form asking "is this the password?", an invitation being looked up.
    // There the server's own words are the useful ones: telling someone who
    // mistyped their password that their "sessie is verlopen" is both wrong and
    // baffling, and it is what this used to say.
    if (path.endsWith("/auth/login") || path.startsWith("/api/invitations/")) {
      throw new ApiError(401, await detailFrom(res, "Onjuiste gebruikersnaam of wachtwoord"));
    }
    // Anywhere else a 401 means the session really is over.
    setToken(null);
    window.location.assign("/login");
    throw new ApiError(401, "Sessie verlopen");
  }
  if (!res.ok) {
    throw new ApiError(res.status, await detailFrom(res, `Er ging iets mis (${res.status})`));
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
  /** Change your own password. Answers with a fresh token, because the change
   *  invalidates every token issued before it — this device's included. */
  changePassword: (current_password: string | null, new_password: string) =>
    request<{ access_token: string; user: User }>("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    }),
  /** End every other session. Also answers with a fresh token for this one. */
  logoutEverywhere: () =>
    request<{ access_token: string; user: User }>("/api/auth/logout-everywhere", {
      method: "POST",
    }),

  // ---- the front door (readable while logged out) ----
  authConfig: () => request<AuthConfig>("/api/auth/config"),
  setSelfRegistration: (self_registration: boolean) =>
    request<AuthConfig>("/api/auth/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ self_registration }),
    }),
  /** Where the browser goes to start an SSO login. A real navigation, not a
   *  fetch: the server answers with a redirect to another origin. */
  oidcLoginUrl: (opts: { next?: string; invite?: string } = {}) => {
    const params = new URLSearchParams({ next: opts.next ?? "/" });
    if (opts.invite) params.set("invite", opts.invite);
    return `/api/auth/oidc/login?${params}`;
  },
  /** Trade the one-time code from an SSO redirect for an ordinary token. */
  oidcExchange: (code: string) =>
    request<{ access_token: string; user: User }>("/api/auth/oidc/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }),
  register: (data: { username: string; display_name: string; password: string }) =>
    request<{ access_token: string; user: User }>("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // ---- automatic backups (beheerder) ----
  scheduledBackups: () => request<ScheduledBackups>("/api/backup/scheduled"),
  runScheduledBackup: () =>
    request<ScheduledBackup>("/api/backup/scheduled/run", { method: "POST" }),
  downloadScheduledBackup: (name: string) =>
    download(`/api/backup/scheduled/${encodeURIComponent(name)}`, name),

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

  // ---- saved outfits ----
  listOutfits: (wardrobeId: number, filters: { occasion?: string; weather?: string; season?: string } = {}) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    Object.entries(filters).forEach(([k, v]) => {
      if (v) sp.set(k, v);
    });
    return request<Outfit[]>(`/api/outfits?${sp}`);
  },
  getOutfit: (id: number) => request<Outfit>(`/api/outfits/${id}`),
  createOutfit: (wardrobeId: number, draft: OutfitDraft) =>
    request<Outfit>(`/api/outfits?wardrobe_id=${wardrobeId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    }),
  updateOutfit: (id: number, draft: OutfitDraft) =>
    request<Outfit>(`/api/outfits/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    }),
  deleteOutfit: (id: number) => request<void>(`/api/outfits/${id}`, { method: "DELETE" }),

  // ---- the wear log (only works once you switch it on) ----
  logWear: (outfitId: number, worn_on?: string) =>
    request<{ outfit_id: number; worn_on: string }>(`/api/outfits/${outfitId}/wear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ worn_on: worn_on ?? null }),
    }),
  unlogWear: (outfitId: number, day: string) =>
    request<void>(`/api/outfits/${outfitId}/wear/${day}`, { method: "DELETE" }),
  wearHistory: (outfitId: number) => request<string[]>(`/api/outfits/${outfitId}/wear`),

  // ---- "je zou dit aan kunnen trekken" ----
  recommendations: (wardrobeId: number, occasion?: string) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    if (occasion) sp.set("occasion", occasion);
    return request<RecommendationPage>(`/api/outfits/recommendations?${sp}`);
  },
  discover: (
    wardrobeId: number,
    filters: { occasion?: string; season?: string; weather?: string[] } = {},
  ) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    if (filters.occasion) sp.set("occasion", filters.occasion);
    if (filters.season) sp.set("season", filters.season);
    if (filters.weather?.length) sp.set("weather", filters.weather.join(","));
    return request<OutfitSuggestion[]>(`/api/outfits/discover?${sp}`);
  },

  // ---- weather ----
  weatherTags: () => request<string[]>("/api/weather/tags"),
  searchPlaces: (q: string) => request<Place[]>(`/api/weather/search?q=${encodeURIComponent(q)}`),
  /** Name the coordinates the browser's location permission just handed us. */
  lookupPlace: (latitude: number, longitude: number) =>
    request<Place>(`/api/weather/lookup?latitude=${latitude}&longitude=${longitude}`),
  currentWeather: () => request<Weather>("/api/weather/current"),

  // ---- per-user preferences, stijl-DNA and the style guide ----
  preferences: () => request<Preferences>("/api/me/preferences"),
  savePreferences: (data: Partial<Preferences>) =>
    request<Preferences>("/api/me/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  styleProfile: () => request<StyleProfile>("/api/me/style"),
  saveStyleProfile: (data: { colors?: string[]; styles?: string[]; occasions?: string[]; notes?: string | null }) =>
    request<StyleProfile>("/api/me/style", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  styleGuide: (wardrobeId: number) =>
    request<StyleGuide>(`/api/me/style-guide?wardrobe_id=${wardrobeId}`),

  // ---- occasions (admin-managed list) ----
  listOccasions: () => request<Occasion[]>("/api/occasions"),
  createOccasion: (name: string) =>
    request<Occasion>("/api/occasions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  deleteOccasion: (id: number) => request<void>(`/api/occasions/${id}`, { method: "DELETE" }),

  // ---- week planner ----
  week: (wardrobeId: number, start?: string) => {
    const sp = new URLSearchParams({ wardrobe_id: String(wardrobeId) });
    if (start) sp.set("start", start);
    return request<Week>(`/api/planner/week?${sp}`);
  },
  planDay: (wardrobeId: number, day: string, outfitId: number | null) =>
    request<DayPlan>(`/api/planner?wardrobe_id=${wardrobeId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day, outfit_id: outfitId }),
    }),

  // ---- trips (reistas) ----
  listTrips: (wardrobeId: number) => request<Trip[]>(`/api/trips?wardrobe_id=${wardrobeId}`),
  getTrip: (id: number) => request<TripDetail>(`/api/trips/${id}`),
  createTrip: (
    wardrobeId: number,
    data: { name: string; destination?: string | null; starts_on?: string | null; ends_on?: string | null; notes?: string | null },
  ) =>
    request<TripDetail>(`/api/trips?wardrobe_id=${wardrobeId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteTrip: (id: number) => request<void>(`/api/trips/${id}`, { method: "DELETE" }),
  addTripOutfit: (tripId: number, outfitId: number) =>
    request<TripDetail>(`/api/trips/${tripId}/outfits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outfit_id: outfitId }),
    }),
  removeTripOutfit: (tripId: number, outfitId: number) =>
    request<TripDetail>(`/api/trips/${tripId}/outfits/${outfitId}`, { method: "DELETE" }),
  setPacked: (tripId: number, itemId: number, packed: boolean) =>
    request<TripDetail>(`/api/trips/${tripId}/packed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_id: itemId, packed }),
    }),

  // ---- aanvullen (tags raden, looks samenstellen) ----
  autofillPreview: (wardrobeId: number, count = 10) =>
    request<AutofillPreview>(`/api/autofill/preview?wardrobe_id=${wardrobeId}&count=${count}`),
  /** Fill in the tags that are obvious. Never overwrites what is already set. */
  autofillTags: (wardrobeId: number, dryRun = false, useAi = false) =>
    request<AutofillTagsResult>(
      `/api/autofill/tags?wardrobe_id=${wardrobeId}&dry_run=${dryRun}&use_ai=${useAi}`,
      { method: "POST" },
    ),
  autofillLooks: (wardrobeId: number, count = 10, useAi = false) =>
    request<AutofillLooksResult>(
      `/api/autofill/looks?wardrobe_id=${wardrobeId}&count=${count}&use_ai=${useAi}`,
      { method: "POST" },
    ),

  // ---- insights ----
  insights: (wardrobeId: number) => request<Insights>(`/api/insights?wardrobe_id=${wardrobeId}`),

  // ---- app version (from backend/app/_version.py) ----
  version: () => request<{ version: string }>("/api/version"),
};

export function photoUrl(item: Item, thumb = false): string | null {
  const name = thumb ? item.thumb_filename : item.photo_filename;
  return name ? `/uploads/${name}` : null;
}

export { ApiError, OfflineError };
