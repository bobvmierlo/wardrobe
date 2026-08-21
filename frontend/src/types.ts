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
  created_by_id: number;
  created_at: string;
}

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

export interface ScrapeResult {
  name: string | null;
  brand: string | null;
  color: string | null;
  price: string | null;
  description: string | null;
  images: string[];
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
