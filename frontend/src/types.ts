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
}

export interface Pair {
  anchor: Item;
  candidate: Item;
}

export interface OutfitPartner {
  item: Item;
  approved_by: string[];
}

export interface Stats {
  item_count: number;
  total_pairs: number;
  judged_by_me: number;
  remaining_for_me: number;
}

// The seasons are a fixed set; multiple can apply to one garment.
export const SEASONS = ["Lente", "Zomer", "Herfst", "Winter", "Alle seizoenen"];
