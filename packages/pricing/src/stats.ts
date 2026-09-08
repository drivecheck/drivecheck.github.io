export function percentile(sorted: number[], p: number): number | null {
  if (sorted.length === 0) return null;
  if (sorted.length === 1) return sorted[0];
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  const w = idx - lo;
  return Math.round(sorted[lo] * (1 - w) + sorted[hi] * w);
}

export function median(values: number[]): number | null {
  const sorted = [...values].sort((a, b) => a - b);
  return percentile(sorted, 0.5);
}

export function removeIqrOutliers(values: number[]): number[] {
  if (values.length < 4) return [...values];
  const sorted = [...values].sort((a, b) => a - b);
  const q1 = percentile(sorted, 0.25);
  const q3 = percentile(sorted, 0.75);
  if (q1 == null || q3 == null) return sorted;
  const iqr = q3 - q1;
  const low = q1 - 1.5 * iqr;
  const high = q3 + 1.5 * iqr;
  return sorted.filter((v) => v >= low && v <= high);
}

/** Czech passenger-car assumption when the user leaves mileage blank (0 / missing). */
export const ASSUMED_ANNUAL_MILEAGE_KM = 15_000;

/**
 * Explicit default km for missing/zero subject mileage.
 * Age includes the current calendar year as a partial year (min 1).
 */
export function assumedMileageKm(
  subjectYear: number,
  asOfYear: number = new Date().getFullYear(),
): number {
  const ageYears = Math.max(1, asOfYear - subjectYear + 1);
  return ageYears * ASSUMED_ANNUAL_MILEAGE_KM;
}

/** Resolve subject km: blank/non-positive → age-based assumption. */
export function effectiveSubjectMileageKm(
  subjectMileageKm: number | null | undefined,
  subjectYear: number,
  asOfYear?: number,
): { mileageKm: number; assumed: boolean } {
  if (subjectMileageKm != null && Number.isFinite(subjectMileageKm) && subjectMileageKm > 0) {
    return { mileageKm: Math.round(subjectMileageKm), assumed: false };
  }
  return { mileageKm: assumedMileageKm(subjectYear, asOfYear), assumed: true };
}

/**
 * Adjust a comp asking price toward the subject's year/km.
 * `comp.price + adj` ≈ what the subject would ask if it matched that listing's
 * other traits.
 *
 * Sign: higher subject km than the comp → negative adj (subject worth less).
 * Cap keeps a single dim from exploding the band on absurd km.
 */
export function mileageYearAdjustmentCzk(opts: {
  subjectYear: number;
  subjectMileageKm: number;
  compYear: number | null;
  compMileageKm: number | null;
  basePriceCzk: number;
}): number {
  const { subjectYear, subjectMileageKm, compYear, compMileageKm, basePriceCzk } = opts;
  let adj = 0;
  if (compMileageKm != null && subjectMileageKm > 0) {
    const deltaKm = compMileageKm - subjectMileageKm;
    // Comp has more km than subject → subject is stronger → raise estimated ask.
    const per10k = Math.max(3_000, Math.round(basePriceCzk * 0.012));
    adj += (deltaKm / 10_000) * per10k;
  }
  if (compYear != null) {
    const deltaYears = subjectYear - compYear;
    adj += deltaYears * Math.max(8_000, Math.round(basePriceCzk * 0.03));
  }
  // Cap absolute correction (~40% of base) so extreme km cannot invert via blow-up.
  const cap = Math.max(40_000, Math.round(basePriceCzk * 0.4));
  return Math.round(Math.max(-cap, Math.min(cap, adj)));
}

export function confidenceFromSample(sampleSize: number, yearWindow: number): {
  level: "low" | "medium" | "high";
  noteCs: string;
} {
  if (sampleSize < 5) {
    return {
      level: "low",
      noteCs: "Málo srovnatelných inzerátů — berte odhad orientačně.",
    };
  }
  if (sampleSize < 15 || yearWindow >= 4) {
    return {
      level: "medium",
      noteCs: "Střední jistota — vzorek je použitelný, ale stále omezený.",
    };
  }
  return {
    level: "high",
    noteCs: "Vysoká jistota — dostatek srovnatelných nabídek.",
  };
}

/**
 * Sum feature premiums into the firm ask, capped so stacked equipment cannot
 * dominate the km/year-normalized core (default ±120k Kč).
 */
export function dampenFeatureDeltas(deltas: number[], maxAbsTotal = 120_000): number {
  const raw = deltas.reduce((a, b) => a + b, 0);
  if (Math.abs(raw) <= maxAbsTotal) return raw;
  return Math.sign(raw) * maxAbsTotal;
}

export function roundToThousand(value: number): number {
  return Math.round(value / 1000) * 1000;
}
