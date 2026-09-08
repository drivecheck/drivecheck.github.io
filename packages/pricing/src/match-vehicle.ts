import { listingHasEquipment } from "./equipment";
import { mapBody, mapDrive, mapFuel, mapTransmission } from "./vehicle-map";

/** Tunable acceptance / soft-score knobs (covered by tests). */
export const MATCH_THRESHOLDS = {
  /** Minimum soft score after hard pass; below → hide (better empty than wrong). */
  minScore: 38,
  /** Year delta where soft year score hits zero (still may pass if other dims strong). */
  yearSoftZeroDelta: 4,
  /** Year delta hard-cap: farther → reject even if make/model ok. */
  yearHardMaxDelta: 8,
  mileageSoftZeroDeltaKm: 120_000,
  powerSoftZeroDeltaKw: 35,
  displacementSoftZeroDeltaCc: 400,
  /** Soft penalty when subject set a dim the listing leaves unknown. */
  unknownDimPenalty: 4,
  featureOverlapBoostPerKey: 4,
  featureOverlapBoostMax: 16,
  titleTokenBoostPerHit: 5,
  titleTokenBoostMax: 15,
} as const;

export type VehicleMatchSubject = {
  make: string;
  model: string;
  year?: number;
  mileageKm?: number;
  fuel?: string;
  transmission?: string;
  body?: string;
  drive?: string;
  powerKw?: number;
  displacementCc?: number;
  /** Soft title tokens (motorizace / generation / trim). */
  motorization?: string;
  generation?: string;
  trim?: string;
  featureKeys?: string[];
};

export type VehicleMatchOffer = {
  make?: string | null;
  model?: string | null;
  title?: string | null;
  year?: number | null;
  mileageKm?: number | null;
  fuel?: string | null;
  transmission?: string | null;
  body?: string | null;
  drive?: string | null;
  powerKw?: number | null;
  displacementCc?: number | null;
  featureKeys?: readonly string[] | null;
};

export type VehicleMatchResult = {
  ok: boolean;
  /** Soft similarity score; only meaningful when hard filters pass. */
  score: number;
  hardRejectReason?: string;
};

/** Normalize make/model tokens for loose Czech-safe matching. */
export function normalizeVehicleToken(value: string | null | undefined): string {
  return (value ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

function tokenPresent(haystack: string, token: string): boolean {
  if (!token) return true;
  if (!haystack) return false;
  if (haystack.includes(token)) return true;
  // Multi-word models: require every significant word (len≥2).
  const parts = token.split(/[\s/-]+/).filter((p) => p.length >= 2);
  if (parts.length <= 1) return false;
  return parts.every((p) => haystack.includes(p));
}

function isBlankOrUnknown(value: string | null | undefined): boolean {
  const n = normalizeVehicleToken(value);
  return !n || n === "neuvedeno" || n === "neznamo" || n === "unknown" || n === "-";
}

/** Canonical fuel bucket, or null when unknown / unmapped. */
export function canonicalFuelKey(raw: string | null | undefined): string | null {
  if (isBlankOrUnknown(raw)) return null;
  const mapped = mapFuel(raw);
  if (mapped) return normalizeVehicleToken(mapped);
  // Fallback: already-canonical Czech labels from listings/catalog.
  const n = normalizeVehicleToken(raw);
  if (/nafta|diesel/.test(n)) return "nafta";
  if (/benzin|petrol|gasoline/.test(n)) return "benzin";
  if (/hybrid/.test(n)) return "hybrid";
  if (/elektro|electric/.test(n)) return "elektro";
  if (/lpg/.test(n) && /benzin/.test(n)) return "benzin+lpg";
  if (/^lpg$/.test(n) || n.includes("lpg")) return "lpg";
  if (/cng/.test(n)) return "cng";
  return n || null;
}

/**
 * Transmission buckets:
 * - manual | automatic | dsg | cvt
 * Policy: DSG is compatible with subject "automatic" (subtype).
 * Subject DSG rejects plain manual; plain "automatic" listing is allowed (soft).
 */
export function canonicalTransmissionKey(
  raw: string | null | undefined,
): "manual" | "automatic" | "dsg" | "cvt" | null {
  if (isBlankOrUnknown(raw)) return null;
  const mapped = mapTransmission(raw);
  const s = normalizeVehicleToken(mapped ?? raw);
  if (/dsg|dvojspoj|dct|dual.?clutch/.test(s)) return "dsg";
  if (/cvt|variator/.test(s)) return "cvt";
  if (/auto|automat/.test(s)) return "automatic";
  if (/manu/.test(s) || /\bmt\b/.test(s)) return "manual";
  return null;
}

function transmissionCompatible(
  want: ReturnType<typeof canonicalTransmissionKey>,
  have: ReturnType<typeof canonicalTransmissionKey>,
): boolean {
  if (!want || !have) return true;
  if (want === have) return true;
  // Subject wants any automatic family → DSG/CVT/automatic all ok.
  if (want === "automatic" && (have === "dsg" || have === "cvt" || have === "automatic")) {
    return true;
  }
  // Subject wants DSG → accept DSG; also allow generic automatic (many ads omit DSG).
  if (want === "dsg" && (have === "dsg" || have === "automatic")) return true;
  // Subject wants CVT → CVT or generic automatic.
  if (want === "cvt" && (have === "cvt" || have === "automatic")) return true;
  return false;
}

export function canonicalBodyKey(raw: string | null | undefined): string | null {
  if (isBlankOrUnknown(raw)) return null;
  const mapped = mapBody(raw);
  if (mapped) return normalizeVehicleToken(mapped);
  const n = normalizeVehicleToken(raw);
  if (/\bkombi\b|\bcombi\b|\bwagon\b|\bestate\b/.test(n)) return "kombi";
  if (/\bhatch/.test(n)) return "hatchback";
  if (/\bsedan\b|\blimuz/.test(n)) return "sedan";
  if (/\bsuv\b|\bterenn/.test(n)) return "suv";
  if (/\bmpv\b|\bminivan\b|\bvan\b/.test(n)) return "mpv";
  if (/\bcoup/.test(n)) return "coupe";
  if (/\bcabrio|\bconvertible\b/.test(n)) return "cabrio";
  if (/\bpick[\s-]?up\b/.test(n)) return "pick-up";
  if (/\bdodavka\b|\bcargo\b/.test(n)) return "dodavka";
  // Unknown free text (e.g. a full title) is not a body — treat as missing.
  return null;
}

export function canonicalDriveKey(raw: string | null | undefined): string | null {
  if (isBlankOrUnknown(raw)) return null;
  const mapped = mapDrive(raw);
  if (mapped) {
    const n = normalizeVehicleToken(mapped);
    if (n.includes("4") || n.includes("awd")) return "awd";
    if (n.includes("predni") || n.includes("fwd")) return "fwd";
    if (n.includes("zadni") || n.includes("rwd")) return "rwd";
  }
  const s = normalizeVehicleToken(raw);
  if (/awd|4x4|4wd|quattro|xdrive|4motion|vsech/.test(s)) return "awd";
  if (/fwd|predni|front/.test(s)) return "fwd";
  if (/rwd|zadni|rear/.test(s)) return "rwd";
  return null;
}

/**
 * Hard dims: make, model (title-authoritative), fuel, transmission, drive, body.
 *
 * Policy:
 * - User specified + listing contradicts → exclude
 * - User specified + listing unknown → allow, soft-penalize (rank lower)
 * - Accident filtering stays elsewhere (SQL / filter-offers)
 */
export function hardMatchVehicle(
  offer: VehicleMatchOffer,
  subject: Pick<
    VehicleMatchSubject,
    "make" | "model" | "fuel" | "transmission" | "body" | "drive" | "year"
  >,
): { ok: true } | { ok: false; reason: string } {
  const wantMake = normalizeVehicleToken(subject.make);
  const wantModel = normalizeVehicleToken(subject.model);
  if (!wantMake || !wantModel) return { ok: false, reason: "subject_incomplete" };

  const make = normalizeVehicleToken(offer.make);
  const model = normalizeVehicleToken(offer.model);
  const title = normalizeVehicleToken(offer.title);

  const makeOk = tokenPresent(make, wantMake) || tokenPresent(title, wantMake);
  if (!makeOk) return { ok: false, reason: "make" };

  if (title) {
    if (!tokenPresent(title, wantModel)) return { ok: false, reason: "model_title" };
  } else if (!tokenPresent(model, wantModel)) {
    return { ok: false, reason: "model" };
  }

  if (subject.fuel) {
    const want = canonicalFuelKey(subject.fuel);
    const have = canonicalFuelKey(offer.fuel);
    if (want && have && want !== have) return { ok: false, reason: "fuel" };
  }

  if (subject.transmission) {
    const want = canonicalTransmissionKey(subject.transmission);
    const have = canonicalTransmissionKey(offer.transmission);
    if (want && have && !transmissionCompatible(want, have)) {
      return { ok: false, reason: "transmission" };
    }
  }

  if (subject.drive) {
    const want = canonicalDriveKey(subject.drive);
    const have = canonicalDriveKey(offer.drive);
    if (want && have && want !== have) return { ok: false, reason: "drive" };
  }

  if (subject.body) {
    const want = canonicalBodyKey(subject.body);
    const have = canonicalBodyKey(offer.body);
    // Body often appears only in title — try title fallback before contradict.
    const haveTitle = have ?? canonicalBodyKey(offer.title);
    if (want && haveTitle && want !== haveTitle) return { ok: false, reason: "body" };
  }

  if (
    subject.year != null &&
    offer.year != null &&
    Math.abs(offer.year - subject.year) > MATCH_THRESHOLDS.yearHardMaxDelta
  ) {
    return { ok: false, reason: "year_hard" };
  }

  return { ok: true };
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function proximityScore(delta: number, zeroAt: number, maxPoints: number): number {
  if (zeroAt <= 0) return 0;
  const t = 1 - Math.min(Math.abs(delta), zeroAt) / zeroAt;
  return maxPoints * t;
}

function titleTokenHits(title: string, rawTokens: Array<string | undefined>): number {
  let hits = 0;
  for (const raw of rawTokens) {
    const token = normalizeVehicleToken(raw);
    if (!token || token.length < 2) continue;
    // Skip ultra-generic / numeric-only crumbs.
    if (/^\d+$/.test(token)) continue;
    const parts = token.split(/[\s/-]+/).filter((p) => p.length >= 2);
    const ok =
      parts.length > 1 ? parts.every((p) => title.includes(p)) : title.includes(token);
    if (ok) hits += 1;
  }
  return hits;
}

/**
 * Soft similarity after a hard pass.
 * Typical band ~25–90 so equipment / year / km still differentiate near the top.
 */
export function softScoreVehicle(
  offer: VehicleMatchOffer,
  subject: VehicleMatchSubject,
): number {
  let score = 42;
  const title = normalizeVehicleToken(offer.title);

  if (subject.year != null) {
    if (offer.year == null) {
      score -= MATCH_THRESHOLDS.unknownDimPenalty;
    } else {
      score += proximityScore(
        offer.year - subject.year,
        MATCH_THRESHOLDS.yearSoftZeroDelta,
        18,
      );
    }
  }

  if (subject.mileageKm != null && subject.mileageKm > 0) {
    if (offer.mileageKm == null) {
      score -= MATCH_THRESHOLDS.unknownDimPenalty;
    } else {
      score += proximityScore(
        offer.mileageKm - subject.mileageKm,
        MATCH_THRESHOLDS.mileageSoftZeroDeltaKm,
        14,
      );
    }
  }

  if (subject.powerKw != null && subject.powerKw > 0) {
    if (offer.powerKw == null) {
      score -= MATCH_THRESHOLDS.unknownDimPenalty;
    } else {
      score += proximityScore(
        offer.powerKw - subject.powerKw,
        MATCH_THRESHOLDS.powerSoftZeroDeltaKw,
        8,
      );
    }
  }

  if (subject.displacementCc != null && subject.displacementCc > 0) {
    if (offer.displacementCc == null) {
      score -= 2;
    } else {
      score += proximityScore(
        offer.displacementCc - subject.displacementCc,
        MATCH_THRESHOLDS.displacementSoftZeroDeltaCc,
        6,
      );
    }
  }

  // Exact hard-dim confirmation bonus (listing not unknown).
  if (subject.fuel && canonicalFuelKey(offer.fuel)) score += 3;
  if (subject.transmission && canonicalTransmissionKey(offer.transmission)) {
    const want = canonicalTransmissionKey(subject.transmission);
    const have = canonicalTransmissionKey(offer.transmission);
    if (want && have && want === have) score += 4;
    else if (want && have) score += 2; // compatible subtype
  }
  if (subject.drive && canonicalDriveKey(offer.drive)) score += 2;
  if (subject.body && (canonicalBodyKey(offer.body) || canonicalBodyKey(offer.title))) {
    score += 2;
  }
  if (subject.fuel && !canonicalFuelKey(offer.fuel)) {
    score -= MATCH_THRESHOLDS.unknownDimPenalty;
  }
  if (subject.transmission && !canonicalTransmissionKey(offer.transmission)) {
    score -= MATCH_THRESHOLDS.unknownDimPenalty;
  }
  if (subject.drive && !canonicalDriveKey(offer.drive)) {
    score -= MATCH_THRESHOLDS.unknownDimPenalty;
  }
  if (
    subject.body &&
    !canonicalBodyKey(offer.body) &&
    !canonicalBodyKey(offer.title)
  ) {
    score -= MATCH_THRESHOLDS.unknownDimPenalty;
  }

  const tokenHits = titleTokenHits(title, [
    subject.motorization,
    subject.generation,
    subject.trim,
  ]);
  score += Math.min(
    MATCH_THRESHOLDS.titleTokenBoostMax,
    tokenHits * MATCH_THRESHOLDS.titleTokenBoostPerHit,
  );

  const wantedFeatures = subject.featureKeys ?? [];
  if (wantedFeatures.length > 0) {
    let overlap = 0;
    for (const key of wantedFeatures) {
      if (listingHasEquipment(offer.featureKeys, key)) overlap += 1;
    }
    score += Math.min(
      MATCH_THRESHOLDS.featureOverlapBoostMax,
      overlap * MATCH_THRESHOLDS.featureOverlapBoostPerKey,
    );
    if ((offer.featureKeys?.length ?? 0) === 0) {
      score -= MATCH_THRESHOLDS.unknownDimPenalty;
    }
  }

  return clamp(Math.round(score), 0, 100);
}

/**
 * Full precision match: hard filters + soft score + min threshold.
 * Use for comps, market-list (DB + live), and client ranking.
 */
export function matchVehicle(
  offer: VehicleMatchOffer,
  subject: VehicleMatchSubject,
  opts?: { minScore?: number },
): VehicleMatchResult {
  const hard = hardMatchVehicle(offer, subject);
  if (!hard.ok) {
    return { ok: false, score: 0, hardRejectReason: hard.reason };
  }
  const score = softScoreVehicle(offer, subject);
  const minScore = opts?.minScore ?? MATCH_THRESHOLDS.minScore;
  if (score < minScore) {
    return { ok: false, score, hardRejectReason: "soft_threshold" };
  }
  return { ok: true, score };
}

/**
 * True when an offer is plausibly the same make/model as the subject.
 * Kept for callers that only need identity; prefer `matchVehicle` for appraisal.
 */
export function offerMatchesVehicle(
  offer: {
    make?: string | null;
    model?: string | null;
    title?: string | null;
  },
  subject: { make: string; model: string },
): boolean {
  return hardMatchVehicle(offer, subject).ok;
}

/** Filter + rank offers by precision match (best first, then cheaper). */
export function filterAndRankOffersByVehicle<T extends VehicleMatchOffer>(
  offers: T[],
  subject: VehicleMatchSubject,
  opts?: { minScore?: number },
): Array<T & { matchScore: number }> {
  const ranked: Array<T & { matchScore: number }> = [];
  for (const offer of offers) {
    const m = matchVehicle(offer, subject, opts);
    if (!m.ok) continue;
    ranked.push({ ...offer, matchScore: m.score });
  }
  ranked.sort((a, b) => {
    if (b.matchScore !== a.matchScore) return b.matchScore - a.matchScore;
    const pa = "priceCzk" in a ? Number((a as { priceCzk?: number }).priceCzk) : 0;
    const pb = "priceCzk" in b ? Number((b as { priceCzk?: number }).priceCzk) : 0;
    return pa - pb;
  });
  return ranked;
}
