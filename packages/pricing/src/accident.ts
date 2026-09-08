/**
 * Detect crashed / heavily damaged vehicles (CZ + DE).
 * Mirrors crawler `drivecheck_crawler.accident` — keep signals in sync.
 *
 * Product: never show accident stock in browse, market offers, or firm comps.
 */

export const ACCIDENT_FEATURE_KEY = "accident_damaged";

const ACCIDENT_PATTERNS: RegExp[] = [
  // Czech
  /\bhavarovan/i,
  /\bhavarie\b/i,
  /\bhavarii\b/i,
  /\bpo\s+nehod/i,
  /\bposkozen/i,
  /\bpoškozen/i,
  /\bpo\s+totalce\b/i,
  /\bpo\s+totalni/i,
  /\btotalk[ae]\b/i,
  /\bna\s+nahradni\s+dily\b/i,
  /\bna\s+náhradní\s+díly\b/i,
  /\bdemontovan/i,
  /\bbouran/i,
  /\bvrak\b/i,
  // German / import
  /\bunfallwagen\b/i,
  /\bunfallfahrzeug\b/i,
  /\bunfall\b/i,
  /\bunfallschaden\b/i,
  /\bbeschadig/i,
  /\bbeschädig/i,
  /\bbastlerfahrzeug\b/i,
  /\bbastler\b/i,
  /\bfrontschaden\b/i,
  /\bheckschaden\b/i,
  /\bgetriebeschaden\b/i,
  /\bmotorschaden\b/i,
  /\btotalschaden\b/i,
  /\baccident[- ]?damaged\b/i,
  /\bsalvage\b/i,
];

const DAMAGE_FEATURE_NEEDLES = new Set([
  ACCIDENT_FEATURE_KEY,
  "accident",
  "damaged",
  "unfall",
  "unfallwagen",
  "bastlerfahrzeug",
  "totalschaden",
  "iscurrentlydamaged",
  "accidentdamaged",
]);

function stripAccents(value: string): string {
  return value.normalize("NFD").replace(/\p{M}/gu, "");
}

export function normalizeAccidentText(value: string | null | undefined): string {
  if (!value) return "";
  return stripAccents(value).toLowerCase().replace(/\s+/g, " ").trim();
}

export function textSuggestsAccidentOrDamage(
  text: string | null | undefined,
): boolean {
  const norm = normalizeAccidentText(text);
  if (!norm) return false;
  return ACCIDENT_PATTERNS.some((re) => re.test(norm));
}

export function featureKeysSuggestAccident(
  featureKeys: readonly string[] | null | undefined,
): boolean {
  if (!featureKeys?.length) return false;
  for (const key of featureKeys) {
    const k = normalizeAccidentText(key).replace(/\s+/g, "_");
    if (DAMAGE_FEATURE_NEEDLES.has(k)) return true;
    if (textSuggestsAccidentOrDamage(key)) return true;
  }
  return false;
}

export function isAccidentOrDamagedListing(opts: {
  title?: string | null;
  textBlobs?: Array<string | null | undefined>;
  featureKeys?: readonly string[] | null;
}): boolean {
  if (featureKeysSuggestAccident(opts.featureKeys)) return true;
  if (textSuggestsAccidentOrDamage(opts.title)) return true;
  for (const blob of opts.textBlobs ?? []) {
    if (textSuggestsAccidentOrDamage(blob)) return true;
  }
  return false;
}

/** Postgres POSIX regex (~*) for title crash signals — keep in sync with patterns above. */
export const ACCIDENT_TITLE_SQL_REGEX =
  "havarovan|havarie|havarii|po[[:space:]]+nehod|poskozen|poškozen|po[[:space:]]+totalce|totalk|nahradni[[:space:]]*dil|náhradní[[:space:]]*díly|demontovan|bouran|[[:<:]]vrak[[:>:]]|unfallwagen|unfallfahrzeug|[[:<:]]unfall[[:>:]]|beschadig|beschädig|bastlerfahrzeug|[[:<:]]bastler[[:>:]]|frontschaden|heckschaden|getriebeschaden|motorschaden|totalschaden|accident[-[:space:]]?damaged|[[:<:]]salvage[[:>:]]";

/** Always-on browse/comps predicate: hide accident stock (feature key + title). */
export function accidentExclusionSql(alias = ""): string {
  const col = (name: string) => (alias ? `${alias}.${name}` : name);
  return `(
    NOT (coalesce(${col("feature_keys")}, ARRAY[]::text[]) && ARRAY['${ACCIDENT_FEATURE_KEY}']::text[])
    AND (
      ${col("title")} IS NULL
      OR ${col("title")} !~* '${ACCIDENT_TITLE_SQL_REGEX}'
    )
  )`;
}
