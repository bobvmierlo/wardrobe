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
  notes: string | null;
  is_favorite: boolean;
  photo_filename: string | null;
  thumb_filename: string | null;
  created_by_id: number;
  created_at: string;
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

// Suggested categories; the form also allows free text.
export const CATEGORIES = [
  "Polo",
  "T-shirt",
  "Overhemd",
  "Blouse",
  "Trui",
  "Vest",
  "Hoodie",
  "Sweater",
  "Broek",
  "Jeans",
  "Chino",
  "Shorts",
  "Rok",
  "Jurk",
  "Jas",
  "Blazer",
  "Bodywarmer",
  "Schoenen",
  "Sneakers",
  "Laarzen",
  "Riem",
  "Sjaal",
  "Muts",
  "Pet",
  "Das",
  "Tas",
];

export const SEASONS = ["Lente", "Zomer", "Herfst", "Winter", "Alle seizoenen"];
