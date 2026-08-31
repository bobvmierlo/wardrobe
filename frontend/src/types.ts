export interface User {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
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
