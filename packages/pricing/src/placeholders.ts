export const PLACEHOLDER_ICON_IDS = [
  "hatchback",
  "sedan",
  "kombi",
  "suv",
  "mpv",
  "coupe",
  "cabrio",
  "pickup",
  "van",
  "car",
] as const;

export type PlaceholderIconId = (typeof PLACEHOLDER_ICON_IDS)[number];

export type PlaceholderTile = {
  icon: PlaceholderIconId;
  tintCss: string;
};

const BODY_TO_ICON: Record<string, PlaceholderIconId> = {
  hatchback: "hatchback",
  sedan: "sedan",
  kombi: "kombi",
  combi: "kombi",
  suv: "suv",
  mpv: "mpv",
  coupe: "coupe",
  cabrio: "cabrio",
  "pick-up": "pickup",
  pickup: "pickup",
  dodávka: "van",
  dodavka: "van",
};

const COLOR_TINT: Record<string, string> = {
  bila: "#F4F1EA",
  bílá: "#F4F1EA",
  white: "#F4F1EA",
  cerna: "#1A1814",
  černá: "#1A1814",
  black: "#1A1814",
  seda: "#8A8580",
  šedá: "#8A8580",
  grey: "#8A8580",
  gray: "#8A8580",
  stribrna: "#C5C1B8",
  stříbrná: "#C5C1B8",
  silver: "#C5C1B8",
  modra: "#3B6EA5",
  modrá: "#3B6EA5",
  blue: "#3B6EA5",
  cervena: "#B33A3A",
  červená: "#B33A3A",
  red: "#B33A3A",
  zelena: "#3F6F4A",
  zelená: "#3F6F4A",
  green: "#3F6F4A",
  zluta: "#D4A017",
  žlutá: "#D4A017",
  yellow: "#D4A017",
  hneda: "#6B4A2B",
  hnědá: "#6B4A2B",
  brown: "#6B4A2B",
  bezova: "#C4B49A",
  béžová: "#C4B49A",
  beige: "#C4B49A",
  oranzova: "#D46A1E",
  oranžová: "#D46A1E",
  orange: "#D46A1E",
  fialova: "#6B4C8A",
  fialová: "#6B4C8A",
  purple: "#6B4C8A",
};

const SOURCE_TINT: Record<string, string> = {
  sauto: "#2F6FED",
  bazos: "#2E7D32",
  tipcars: "#E65100",
  autobazar_eu: "#6A1B9A",
  autoscout24: "#C62828",
  mobile_de: "#C4A574",
};

function foldToken(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

function stableIndex(key: string, size: number): number {
  let hash = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash) % size;
}

function iconFromBody(body: string | null | undefined): PlaceholderIconId | null {
  if (!body?.trim()) return null;
  const folded = foldToken(body);
  for (const [token, icon] of Object.entries(BODY_TO_ICON)) {
    if (folded.includes(foldToken(token))) return icon;
  }
  return null;
}

function tintFromColor(color: string | null | undefined): string | null {
  if (!color?.trim()) return null;
  const folded = foldToken(color);
  const entries = Object.entries(COLOR_TINT).sort(
    (left, right) => foldToken(right[0]).length - foldToken(left[0]).length,
  );
  for (const [token, tint] of entries) {
    const foldedToken = foldToken(token);
    if (
      folded === foldedToken ||
      folded.startsWith(`${foldedToken} `) ||
      folded.startsWith(`${foldedToken}-`)
    ) {
      return tint;
    }
  }
  return null;
}

export function placeholderIconId(input: {
  body?: string | null;
  color?: string | null;
  source: string;
  externalId: string;
}): PlaceholderTile {
  const fromBody = iconFromBody(input.body);
  const icon =
    fromBody ??
    PLACEHOLDER_ICON_IDS[
      stableIndex(`${input.source}:${input.externalId}`, PLACEHOLDER_ICON_IDS.length)
    ];
  const tintCss =
    tintFromColor(input.color) ?? SOURCE_TINT[input.source] ?? "#C4A574";
  return { icon, tintCss };
}

/** Cards must never show this string. */
export function placeholderCaption(): string {
  return "";
}
