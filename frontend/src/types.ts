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

export interface SizeOption {
  id: number;
  label: string;
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
