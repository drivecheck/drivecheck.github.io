const BODY_TOKENS: { re: RegExp; body: string }[] = [
  { re: /\bkombi\b|\bcombi\b|\bwagon\b|\bestate\b/i, body: "Kombi" },
  { re: /\bhatchback\b|\bhatch\b/i, body: "Hatchback" },
  { re: /\bsedan\b|\blimousine\b|\blimuz[ií]na\b/i, body: "Sedan" },
  { re: /\bsuv\b|\bter[eé]nn/i, body: "SUV" },
  { re: /\bmpv\b|\bvan\b|\bminivan\b/i, body: "MPV" },
  { re: /\bcoup[eé]\b/i, body: "Coupe" },
  { re: /\bcabrio|\bcabriolet|\bconvertible\b/i, body: "Cabrio" },
  { re: /\bpick[\s-]?up\b/i, body: "Pick-up" },
  { re: /\bdod[aá]vka\b|\bcargo\b/i, body: "Dodávka" },
];

export function mapFuel(raw: string | undefined | null): string | undefined {
  if (!raw?.trim()) return undefined;
  const s = raw.trim().toLowerCase();
  if (/elektro|electric|battery|bev/.test(s)) return "Elektro";
  if (/hybrid|phev|mhev/.test(s)) return "Hybrid";
  if (/benz.*lpg|lpg.*benz|ba\s*\+?\s*lpg/.test(s)) return "Benzín+LPG";
  if (/\blpg\b/.test(s)) return "LPG";
  if (/\bcng\b|zemní plyn|natural gas/.test(s)) return "CNG";
  if (/nafta|diesel|nm\b|gasoil/.test(s)) return "Nafta";
  if (/benz|gasoline|petrol|ba\s*9|ba95|ba98/.test(s)) return "Benzín";
  return undefined;
}

export function mapBody(raw: string | undefined | null): string | undefined {
  if (!raw?.trim()) return undefined;
  for (const { re, body } of BODY_TOKENS) {
    if (re.test(raw)) return body;
  }
  return undefined;
}

export function mapTransmission(raw: string | undefined | null): string | undefined {
  if (!raw?.trim()) return undefined;
  const s = raw.toLowerCase();
  if (/dsg|dct|dual.?clutch|dvojspoj/.test(s)) return "DSG / dvojspojka";
  if (/cvt|variator/.test(s)) return "CVT";
  if (/auto|automat/.test(s)) return "Automatická";
  if (/manual|manu[aá]l|mt\b/.test(s)) return "Manuální";
  return undefined;
}

export function mapDrive(raw: string | undefined | null): string | undefined {
  if (!raw?.trim()) return undefined;
  const s = raw.trim().toLowerCase();
  if (/awd|4x4|4wd|all.?wheel|všech|vsech|pohon všech/.test(s)) return "4×4 / AWD";
  if (/fwd|přední|predni|front/.test(s)) return "Přední";
  if (/rwd|zadní|zadni|rear/.test(s)) return "Zadní";
  return undefined;
}
