/** Turning a colour *word* into a colour you can actually paint with.
 *
 * Garments carry free text ("donkerblauw", "cognac", "gebroken wit"), which is
 * how people describe clothes and how the suggestion engine wants them. A
 * swatch needs a hex value. This is the one place that bridges the two, so
 * every screen that draws a colour draws the same one.
 *
 * The base names mirror `backend/app/suggestions.py:_COLOR_ALIASES` — that is
 * the vocabulary the server normalises to, and what Inzichten counts by. The
 * hexes are muted rather than saturated on purpose: these are swatches for
 * clothing, and a fire-engine red next to a beige reads as an error message.
 */

/** The base palette, keyed by the names the backend normalises to. */
const BASE: Record<string, string> = {
  zwart: "#1b1b1f",
  wit: "#f4f1ea",
  grijs: "#9aa0a6",
  beige: "#cbb99a",
  bruin: "#7a5233",
  blauw: "#4a7fb5",
  navy: "#20304f",
  denim: "#5877a1",
  rood: "#9d2f2a",
  roze: "#e0a7b4",
  oranje: "#c96a2e",
  geel: "#d8ad3c",
  groen: "#5b7a4a",
  paars: "#6f5288",
  goud: "#bd9540",
};

/** Words that mean one of the base colours. Mirrors the backend's aliases, so
 *  a garment the server counted as "navy" is drawn navy here too. */
const ALIASES: Record<string, string> = {
  black: "zwart",
  white: "wit",
  "gebroken wit": "wit",
  creme: "wit",
  crème: "wit",
  "off-white": "wit",
  ecru: "wit",
  gray: "grijs",
  grey: "grijs",
  antraciet: "grijs",
  lichtgrijs: "grijs",
  zilver: "grijs",
  zand: "beige",
  khaki: "beige",
  kaki: "beige",
  camel: "beige",
  taupe: "beige",
  brown: "bruin",
  cognac: "bruin",
  chocolade: "bruin",
  blue: "blauw",
  lichtblauw: "blauw",
  donkerblauw: "navy",
  marineblauw: "navy",
  marine: "navy",
  jeans: "denim",
  spijker: "denim",
  red: "rood",
  bordeaux: "rood",
  bordeauxrood: "rood",
  wijnrood: "rood",
  pink: "roze",
  oudroze: "roze",
  orange: "oranje",
  terracotta: "oranje",
  yellow: "geel",
  okergeel: "geel",
  oker: "geel",
  green: "groen",
  olijf: "groen",
  olijfgroen: "groen",
  legergroen: "groen",
  mint: "groen",
  purple: "paars",
  lila: "paars",
  violet: "paars",
  gold: "goud",
};

/** The base colour name for a free-text colour, or null when it means nothing
 *  the app knows. Same rules as the backend: exact alias first, then any known
 *  word inside a longer description ("donkerblauwe polo"). */
export function baseColor(color: string | null | undefined): string | null {
  const key = (color ?? "").trim().toLowerCase();
  if (!key) return null;
  if (key in BASE) return key;
  if (key in ALIASES) return ALIASES[key];
  for (const [word, base] of Object.entries(ALIASES)) {
    if (key.includes(word)) return base;
  }
  for (const word of Object.keys(BASE)) {
    if (key.includes(word)) return word;
  }
  return null;
}

/** A hex value to paint this colour word with.
 *
 * Falls back to a neutral grey rather than to nothing: a swatch that is absent
 * for some garments and present for others makes a row of them unreadable,
 * and "we don't know this word" is itself worth showing as plain grey.
 */
export function colorHex(color: string | null | undefined): string {
  const base = baseColor(color);
  return base ? BASE[base] : "#8b8b93";
}

/** Whether the app recognises this colour word at all. */
export function isKnownColor(color: string | null | undefined): boolean {
  return baseColor(color) !== null;
}
