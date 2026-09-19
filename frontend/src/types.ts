export interface User {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  /** "local" or "oidc" — how this account signs in. Optional because a
   *  response cached by the service worker may predate the field. */
  auth_provider?: string;
}

export interface Item {
  id: number;
  name: string;
  category: string;
  brand: string | null;
  color: string | null;
  size: string | null;
  season: string | null;
  seasons: string[];
  /** Comma-separated on the wire; the arrays beside them are what to read. */
  occasion: string | null;
  occasions: string[];
  weather: string | null;
  weather_tags: string[];
  style: string | null;
  style_tags: string[];
  notes: string | null;
  is_favorite: boolean;
  photo_filename: string | null;
  thumb_filename: string | null;
  wardrobe_id: number | null;
  created_by_id: number;
  created_at: string;
}

// A member's role on someone else's wardrobe.
export type MemberRole = "editor" | "viewer";
// The current user's effective role on a wardrobe.
export type WardrobeRole = "owner" | "admin" | MemberRole;

export interface Wardrobe {
  id: number;
  name: string;
  owner: User;
  my_role: WardrobeRole;
  can_edit: boolean;
  can_manage: boolean;
  member_count: number;
}

export interface WardrobeMember {
  user: User;
  role: MemberRole;
}

export const ROLE_LABELS: Record<WardrobeRole, string> = {
  owner: "Eigenaar",
  admin: "Beheerder",
  editor: "Bewerker",
  viewer: "Kijker",
};

export interface Category {
  id: number;
  name: string;
}

export type SizeKind = "clothing" | "shoes" | "accessory";

export interface SizeOption {
  id: number;
  label: string;
  kind: SizeKind;
}

export const SIZE_KIND_LABELS: Record<SizeKind, string> = {
  clothing: "Kleding",
  shoes: "Schoenen",
  accessory: "One-size / accessoires",
};

// Best-effort mapping from a (free-text) category name to the most relevant
// size kind, mirroring the backend category groups. Used to surface the right
// sizes first in the form.
const SHOE_WORDS = ["schoen", "sneaker", "laars", "boot", "sanda", "pump", "hak"];
const ACCESSORY_WORDS = ["muts", "pet", "sjaal", "das", "hoed", "cap", "tas", "sok", "handschoen"];

export function sizeKindForCategory(category: string): SizeKind {
  const c = category.toLowerCase();
  if (SHOE_WORDS.some((w) => c.includes(w))) return "shoes";
  if (ACCESSORY_WORDS.some((w) => c.includes(w))) return "accessory";
  return "clothing";
}

// Standard letter-size order, plus common numeric aliases (2XL = XXL, ...).
const LETTER_RANK: Record<string, number> = {};
["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL"].forEach((s, i) => {
  LETTER_RANK[s] = i;
});
LETTER_RANK["2XL"] = LETTER_RANK["XXL"];
LETTER_RANK["3XL"] = LETTER_RANK["XXXL"];
LETTER_RANK["4XL"] = LETTER_RANK["XXXXL"];

// Sort key that puts letter sizes first (in their standard order), then
// numeric sizes ascending, then anything else alphabetically.
function sizeSortKey(label: string): [number, number, string] {
  const l = label.trim().toUpperCase();
  if (l in LETTER_RANK) return [0, LETTER_RANK[l], l];
  if (/^\d+([.,]\d+)?$/.test(l)) return [1, parseFloat(l.replace(",", ".")), l];
  return [2, 0, l];
}

/** Compare two sizes so a dropdown lists them in a logical order. */
export function compareSizes(a: SizeOption, b: SizeOption): number {
  const ka = sizeSortKey(a.label);
  const kb = sizeSortKey(b.label);
  if (ka[0] !== kb[0]) return ka[0] - kb[0];
  if (ka[1] !== kb[1]) return ka[1] - kb[1];
  return ka[2].localeCompare(kb[2], "nl", { numeric: true });
}

export interface ScrapeResult {
  name: string | null;
  brand: string | null;
  color: string | null;
  price: string | null;
  description: string | null;
  images: string[];
}

export interface ColorRule {
  id: number;
  color_a: string;
  color_b: string;
  verdict: "good" | "bad";
}

export interface ColorLogic {
  rules: ColorRule[];
  neutrals: string[];
  colors: string[];
}

export interface OutfitSuggestion {
  items: Item[];
  score: number;
  reason: string;
  /** Always false in practice: suggestions that are already a combination are
   *  filtered out server-side. Kept so the UI can disable "accepteren". */
  already_combined: boolean;
}

/** Two garments to judge. Always the same way round, whichever garment the
 *  queue was anchored on: the bovenstuk left, the onderstuk right. */
export interface Pair {
  /** The bovenstuk: shown on the left. */
  anchor: Item;
  /** The onderstuk: the card being swiped, on the right. */
  candidate: Item;
  /** True when this pair was skipped earlier and has come back around. */
  skipped: boolean;
}

export type Verdict = "yes" | "no";

export interface PairVote {
  user_id: number;
  display_name: string;
  verdict: Verdict;
}

/** A pair the current user already judged, shown in the "ongedaan maken" list. */
export interface JudgedPair {
  item_a: Item;
  item_b: Item;
  my_verdict: Verdict;
  votes: PairVote[];
  updated_at: string;
}

export interface OutfitPartner {
  item: Item;
  approved_by: string[];
}

/** A garment judged *not* to go with this one. Shown on a kledingstuk's own
 *  page, never on Outfits — a rejected pair is not an outfit. */
export interface RejectedPartner {
  item: Item;
  rejected_by: string[];
  /** Members who said yes anyway; non-empty means the household is split. */
  approved_by: string[];
  /** Only your own "nee" is yours to withdraw. */
  rejected_by_me: boolean;
}

export interface Stats {
  item_count: number;
  total_pairs: number;
  judged_by_me: number;
  skipped_by_me: number;
  remaining_for_me: number;
}

/** What the login screen is allowed to offer someone without an account. */
export interface AuthConfig {
  /** True when anyone may create their own account; false = invitation only. */
  self_registration: boolean;
  /** True when the server has a working SSO provider to offer. */
  oidc_enabled: boolean;
  /** Text for the SSO button, chosen by whoever runs the server. */
  oidc_label: string;
  /** True when a group at the provider decides who is a beheerder, so the
   *  accounts screen must not offer a button that would be overwritten. */
  oidc_manages_admins: boolean;
  /** Shortest password this installation accepts, so a form can say so before
   *  the server has to refuse anything. */
  min_password_length: number;
  /** Whether to show the username/password form straight away. The form is
   *  always reachable either way — that is the break-glass for when the
   *  provider is down. */
  local_login: boolean;
}

// ---- invitation links ----
export type InvitationStatus = "open" | "accepted" | "expired" | "revoked";

/** "wardrobe" shares an existing kast; "account" only creates a login. */
export type InvitationKind = "wardrobe" | "account";

export const INVITATION_STATUS_LABELS: Record<InvitationStatus, string> = {
  open: "Nog te gebruiken",
  accepted: "Gebruikt",
  expired: "Verlopen",
  revoked: "Ingetrokken",
};

export interface Invitation {
  id: number;
  token: string;
  kind: InvitationKind;
  /** The kast being shared — null for an account link, which shares none. */
  wardrobe_name: string | null;
  /** Path to open in a browser, e.g. "/invite/abc". Combine with the current
   *  origin to get the full link to share. */
  path: string;
  /** Null for an account link: there is no kast to have a role on. */
  role: MemberRole | null;
  label: string | null;
  status: InvitationStatus;
  created_at: string;
  expires_at: string | null;
  accepted_at: string | null;
  accepted_by: User | null;
}

/** What the holder of a link is told before signing in or registering.
 *  An account link shares no kast, so it leaves those fields empty. */
export interface InvitationInfo {
  kind: InvitationKind;
  wardrobe_name: string | null;
  owner_name: string | null;
  role: MemberRole | null;
  label: string | null;
  status: InvitationStatus;
  expires_at: string | null;
}

// ---- logging & audit trail (beheerder) ----
export interface AuditEntry {
  id: number;
  created_at: string;
  action: string;
  action_label: string;
  user_id: number | null;
  user_name: string;
  wardrobe_id: number | null;
  wardrobe_name: string | null;
  entity_type: string | null;
  entity_id: number | null;
  detail: string;
}

export interface AuditPage {
  entries: AuditEntry[];
  total: number;
  actions: string[];
}

export interface LogEntry {
  id: number;
  time: string;
  level: string;
  logger: string;
  message: string;
}

// The seasons are a fixed set; multiple can apply to one garment.
export const SEASONS = ["Lente", "Zomer", "Herfst", "Winter", "Alle seizoenen"];

/** What a beheerder is told about an archive before restoring it. */
export interface BackupPreview {
  scope: "wardrobe" | "instance";
  app_version: string;
  generated_at: string;
  generated_by: string;
  wardrobe_names: string[];
  wardrobes: number;
  people: number;
  items: number;
  outfits: number;
  combinations: number;
  skipped: number;
  photos: number;
}

/** What a restore actually changed. */
export interface RestoreResult {
  mode: "merge" | "replace";
  wardrobe: string;
  added: number;
  updated: number;
  outfits: number;
  combinations: number;
  skipped_pairs: number;
  photos: number;
}

/** A kast a beheerder can restore into. */
export interface RestoreTarget {
  id: number;
  name: string;
  owner: string;
}

// ---- automatic backups ----
/** One backup file the schedule has written. */
export interface ScheduledBackup {
  name: string;
  size_bytes: number;
  created_at: string;
}

/** The schedule, and what it has produced so far. */
export interface ScheduledBackups {
  /** "UU:MM", or empty when no schedule is set. */
  time: string;
  keep: number;
  /** False when unset *or* unparseable — the log says which. */
  enabled: boolean;
  backups: ScheduledBackup[];
}

// ---- Tags, outfits and everything built on them ----

/** The weather vocabulary garments and outfits are tagged with. Mirrors
 *  ``app/tags.py``; the backend also serves it at /api/weather/tags. */
export const WEATHER_TAGS = [
  "Zonnig",
  "Bewolkt",
  "Regen",
  "Sneeuw",
  "Winderig",
  "Koud",
  "Mild",
  "Warm",
  "Heet",
];

/** Which of those are temperatures rather than skies — the planner and the
 *  "Vandaag" card draw them differently. */
export const TEMPERATURE_TAGS = ["Koud", "Mild", "Warm", "Heet"];

export const WEATHER_ICONS: Record<string, string> = {
  Zonnig: "☀️",
  Bewolkt: "☁️",
  Regen: "🌧️",
  Sneeuw: "❄️",
  Winderig: "💨",
  Koud: "🥶",
  Mild: "🌤️",
  Warm: "🌞",
  Heet: "🔥",
};

export interface Occasion {
  id: number;
  name: string;
}

export interface Outfit {
  id: number;
  name: string;
  notes: string | null;
  items: Item[];
  seasons: string[];
  occasions: string[];
  weather_tags: string[];
  style_tags: string[];
  created_by_id: number;
  created_at: string;
  /** Your own history only — never anybody else's. */
  wear_count: number;
  last_worn: string | null;
}

export interface OutfitDraft {
  name: string;
  item_ids: number[];
  notes?: string | null;
  seasons?: string[];
  occasions?: string[];
  weather_tags?: string[];
  style_tags?: string[];
}

export interface Weather {
  location: string;
  description: string;
  temperature: number;
  apparent_temperature: number;
  wind_speed: number;
  precipitation: number;
  precipitation_chance: number | null;
  high: number | null;
  low: number | null;
  is_day: boolean;
  tags: string[];
  mode: string;
}

export interface Place {
  name: string;
  label: string;
  latitude: number;
  longitude: number;
  region: string | null;
  country: string | null;
  postcode: string | null;
}

export interface Recommendation {
  items: Item[];
  score: number;
  reason: string;
  /** "saved" = an outfit you put together before, "new" = assembled just now. */
  source: "saved" | "new";
  outfit_id: number | null;
  outfit_name: string | null;
  last_worn: string | null;
}

export interface RecommendationPage {
  weather: Weather | null;
  advice: string;
  occasion: string | null;
  recommendations: Recommendation[];
  empty_reason: string | null;
}

export interface TemperatureOption {
  /** Shift in degrees on the temperature bands. Positive = feels warm sooner. */
  value: number;
  label: string;
  hint: string;
}

export interface Preferences {
  theme: string;
  wear_log_enabled: boolean;
  location_label: string | null;
  latitude: number | null;
  longitude: number | null;
  weather_mode: "auto" | "manual";
  manual_weather: string[];
  weather_available: boolean;
  /** How this person experiences temperature, in degrees of shift. */
  temperature_preference: number;
  temperature_options: TemperatureOption[];
}

export interface DayPlan {
  day: string;
  outfit: Outfit | null;
  weather: Weather | null;
}

export interface Week {
  start: string;
  days: DayPlan[];
}

export interface PackingEntry {
  item: Item;
  packed: boolean;
  used_in: number;
}

export interface Trip {
  id: number;
  name: string;
  destination: string | null;
  starts_on: string | null;
  ends_on: string | null;
  notes: string | null;
  outfit_count: number;
  item_count: number;
  packed_count: number;
}

export interface TripDetail extends Trip {
  outfits: Outfit[];
  packing: PackingEntry[];
}

export interface StyleProfile {
  colors: string[];
  styles: string[];
  occasions: string[];
  notes: string | null;
  available_colors: string[];
  available_styles: string[];
  available_occasions: string[];
}

export interface GuideColor {
  color: string;
  count: number;
  goes_with: string[];
  clashes_with: string[];
  in_profile: boolean;
}

export interface StyleGuide {
  colors: GuideColor[];
  neutrals: string[];
  gaps: { title: string; detail: string }[];
  uncovered_weather: string[];
  tips: string[];
}

export interface Insights {
  item_count: number;
  outfit_count: number;
  favorite_count: number;
  unused_items: Item[];
  by_category: { label: string; count: number }[];
  by_season: { label: string; count: number }[];
  by_occasion: { label: string; count: number }[];
  palette: { color: string; count: number }[];
  wear_log_enabled: boolean;
  total_wears: number;
  most_worn: Outfit[];
  neglected: Item[];
}

/** The colour schemes someone can pick in Instellingen.
 *
 * The key is what the server stores; the palette itself lives in styles.css
 * under ``[data-theme="…"]``. Adding one is a change in two places on purpose:
 * the server deliberately does not validate the name, so a new palette needs
 * no backend release. */
export const THEMES: { id: string; label: string; hint: string; swatch: string[] }[] = [
  {
    id: "midnight",
    label: "Middernacht",
    hint: "Donker en rustig — de vertrouwde kleuren van de app.",
    swatch: ["#0f172a", "#1e293b", "#38bdf8"],
  },
  {
    id: "warmzand",
    label: "Warm zand",
    hint: "Licht, warm en papierachtig, met cognac als accent.",
    swatch: ["#f6f1e8", "#fffdf9", "#9a5b34"],
  },
  {
    id: "olijf",
    label: "Olijf",
    hint: "Gedempt groen op een zachte, warme ondergrond.",
    swatch: ["#f3f2ea", "#fbfbf6", "#5d6b3f"],
  },
  {
    id: "bos",
    label: "Bos",
    hint: "Donker met groen — als middernacht, maar warmer.",
    swatch: ["#131a15", "#1d2720", "#7fb685"],
  },
  {
    id: "inkt",
    label: "Inkt",
    hint: "Bijna zwart, met één helder accent. Rustig voor de ogen.",
    swatch: ["#101014", "#1b1b21", "#c9a227"],
  },
];

// ---- Aanvullen: tags raden en looks samenstellen voor een bestaande kast ----

export interface AutofillPreview {
  item_count: number;
  without_weather: number;
  without_occasion: number;
  /** How many of those the app can actually fill in. */
  taggable: number;
  outfit_count: number;
  /** How many new looks it could build right now. */
  composable: number;
  /** Why none can be built, when none can be. */
  composable_reason: string | null;
  /** Whether this installation has the optional AI layer configured. */
  ai_available: boolean;
}

export interface TaggedItem {
  id: number;
  name: string;
  category: string;
  weather: string[];
  occasions: string[];
}

export interface AutofillTagsResult {
  tagged: number;
  examples: TaggedItem[];
  /** How many of those came from the AI rather than the rules. */
  by_ai: number;
  /** Set when the AI was asked for but could not be reached. */
  ai_note: string | null;
}

export interface AutofillLooksResult {
  created: Outfit[];
  note: string | null;
  /** How many of these the AI composed; the rest the app built itself. */
  by_ai: number;
  ai_note: string | null;
}

// ---- De AI-laag, zoals een beheerder 'm in de app instelt ----

export interface AiModelOption {
  value: string;
  label: string;
}

export interface AiSettings {
  enabled: boolean;
  model: string;
  effort: string;
  /** Whether a key is stored, and its last four characters. The key itself
   *  never leaves the server — not even to a beheerder. */
  key_set: boolean;
  key_hint: string | null;
  /** Fields pinned in the server's environment, so not editable here. */
  locked: string[];
  models: AiModelOption[];
  efforts: string[];
  timeout_seconds: number;
}
