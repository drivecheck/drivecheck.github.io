import type { CompListing, ConfidenceLevel } from "@drivecheck/shared";
import {
  effectiveSubjectMileageKm,
  median,
  mileageYearAdjustmentCzk,
  percentile,
  removeIqrOutliers,
  roundToThousand,
} from "./stats";

/**
 * Ideal firm asking price: comps normalized to subject km/year, feature
 * premiums, soft pull toward the dealer band and the liquid p35–p50 zone,
 * then softly clamped. High subject km may sit below the raw market floor.
 */
export function computeFirmEstimate(opts: {
  comps: CompListing[];
  subjectYear: number;
  subjectMileageKm: number;
  featureAdjCzk: number;
}): {
  suggestedPriceCzk: number | null;
  normalizedMedianCzk: number | null;
  marketP25Czk: number | null;
  marketP75Czk: number | null;
  mileageAssumed: boolean;
  effectiveMileageKm: number;
} {
  const { comps, subjectYear, featureAdjCzk } = opts;
  const { mileageKm: subjectMileageKm, assumed: mileageAssumed } =
    effectiveSubjectMileageKm(opts.subjectMileageKm, subjectYear);

  if (comps.length === 0) {
    return {
      suggestedPriceCzk: null,
      normalizedMedianCzk: null,
      marketP25Czk: null,
      marketP75Czk: null,
      mileageAssumed,
      effectiveMileageKm: subjectMileageKm,
    };
  }

  const rawSorted = comps.map((c) => c.priceCzk).sort((a, b) => a - b);
  const cleanRaw = removeIqrOutliers(rawSorted).sort((a, b) => a - b);
  const marketP25Czk = percentile(cleanRaw, 0.25);
  const marketP75Czk = percentile(cleanRaw, 0.75);
  const marketMedian = percentile(cleanRaw, 0.5);

  const compMiles = comps
    .map((c) => c.mileageKm)
    .filter((km): km is number => km != null && km > 0);
  const medianCompKm = median(compMiles);

  const normalized = comps
    .map((c) => {
      const base = marketMedian ?? c.priceCzk;
      const adj = mileageYearAdjustmentCzk({
        subjectYear,
        subjectMileageKm,
        compYear: c.year,
        compMileageKm: c.mileageKm,
        basePriceCzk: base,
      });
      return c.priceCzk + adj;
    })
    .filter((v) => Number.isFinite(v) && v > 0);

  const cleanNorm = removeIqrOutliers(normalized).sort((a, b) => a - b);
  const normalizedMedianCzk = percentile(cleanNorm, 0.5);
  const p35 = percentile(cleanNorm, 0.35);
  const p50 = normalizedMedianCzk;

  const dealerNorm = comps
    .filter((c) => c.sellerType === "dealer")
    .map((c) => {
      const base = marketMedian ?? c.priceCzk;
      return (
        c.priceCzk +
        mileageYearAdjustmentCzk({
          subjectYear,
          subjectMileageKm,
          compYear: c.year,
          compMileageKm: c.mileageKm,
          basePriceCzk: base,
        })
      );
    });
  const dealerClean = removeIqrOutliers(dealerNorm);
  const dealerMedian =
    dealerClean.length >= 5 ? percentile(dealerClean.sort((a, b) => a - b), 0.5) : null;

  if (p50 == null) {
    return {
      suggestedPriceCzk: null,
      normalizedMedianCzk: null,
      marketP25Czk: marketP25Czk != null ? roundToThousand(marketP25Czk) : null,
      marketP75Czk: marketP75Czk != null ? roundToThousand(marketP75Czk) : null,
      mileageAssumed,
      effectiveMileageKm: subjectMileageKm,
    };
  }

  // Liquid firm zone: between p35 and median of normalized comps.
  const liquidCore =
    p35 != null ? Math.round(p35 * 0.45 + p50 * 0.55) : p50;

  // Compete with dealers when we know their band; else stay on liquid core.
  const withDealer =
    dealerMedian != null
      ? Math.round(liquidCore * 0.65 + dealerMedian * 0.35)
      : liquidCore;

  let suggested = withDealer + featureAdjCzk;

  // Corridor: never above raw market ceiling. High-km subjects may sit below
  // the raw floor — clamping them up was inverting mileage monotonicity.
  if (marketP25Czk != null && marketP75Czk != null) {
    const hi = marketP75Czk * 1.03;
    suggested = Math.min(hi, suggested);
    const highKmVsComps =
      medianCompKm != null && subjectMileageKm > medianCompKm * 1.35;
    if (highKmVsComps) {
      suggested = Math.max(marketP25Czk * 0.55, suggested);
    } else {
      suggested = Math.max(marketP25Czk * 0.97, suggested);
    }
  }

  return {
    suggestedPriceCzk: roundToThousand(suggested),
    normalizedMedianCzk: roundToThousand(p50 + featureAdjCzk),
    marketP25Czk: marketP25Czk != null ? roundToThousand(marketP25Czk) : null,
    marketP75Czk: marketP75Czk != null ? roundToThousand(marketP75Czk) : null,
    mileageAssumed,
    effectiveMileageKm: subjectMileageKm,
  };
}

export function confidenceFromAppraisal(opts: {
  sampleSize: number;
  yearWindow: number;
  priceLowCzk: number | null;
  priceHighCzk: number | null;
  priceTypicalCzk: number | null;
  featureCount: number;
  featureLowConfidenceCount: number;
  /** Subject km was blank/0 — age-based assumption. */
  mileageAssumed?: boolean;
  /** Subject effective km at/above extreme threshold. */
  extremeMileage?: boolean;
  /** Sold-proxy sample; 0–2 means confidence cannot be high. */
  soldProxyCount?: number;
}): { level: ConfidenceLevel; noteCs: string } {
  const {
    sampleSize,
    yearWindow,
    priceLowCzk,
    priceHighCzk,
    priceTypicalCzk,
    featureCount,
    featureLowConfidenceCount,
    mileageAssumed = false,
    extremeMileage = false,
    soldProxyCount,
  } = opts;

  let score = 0;
  if (sampleSize >= 25) score += 3;
  else if (sampleSize >= 15) score += 2;
  else if (sampleSize >= 8) score += 1;
  else if (sampleSize >= 5) score += 0;
  else score -= 2;

  if (yearWindow <= 2) score += 1;
  else if (yearWindow >= 6) score -= 1;

  if (
    priceLowCzk != null &&
    priceHighCzk != null &&
    priceTypicalCzk != null &&
    priceTypicalCzk > 0
  ) {
    const iqrRatio = (priceHighCzk - priceLowCzk) / priceTypicalCzk;
    if (iqrRatio < 0.18) score += 1;
    else if (iqrRatio > 0.4) score -= 1;
    if (iqrRatio > 0.55) score -= 1;
  }

  if (featureCount > 0) {
    const lowShare = featureLowConfidenceCount / featureCount;
    if (lowShare > 0.6) score -= 1;
    else if (lowShare < 0.25 && featureCount >= 2) score += 1;
  }

  // Assumed / extreme km weaken the firm number even when the sample looks dense.
  if (mileageAssumed) score -= 1;
  if (extremeMileage) score -= 1;

  // Cannot claim "high" when km is assumed or extreme — floor the badge.
  const kmWeak = mileageAssumed || extremeMileage;
  const soldWeak = soldProxyCount != null && soldProxyCount < 3;

  if (score >= 3 && !kmWeak && !soldWeak) {
    return {
      level: "high",
      noteCs: "Vysoká jistota — hustý vzorek, úzké pásmo a stabilní korekce výbavy.",
    };
  }
  if (score >= 1 || (kmWeak && score >= 0)) {
    return {
      level: "medium",
      noteCs: soldWeak
        ? "Střední jistota — málo indicií o skutečných prodejích; číslo vychází hlavně z inzerátů."
        : kmWeak
          ? "Střední jistota — nájezd je odhadnutý nebo extrémní; ověřte km a stav."
          : "Střední jistota — odhad je použitelný, ale citlivý na doplnění parametrů.",
    };
  }
  return {
    level: "low",
    noteCs: "Nižší jistota — málo shod nebo široké ceny; berte číslo orientačně.",
  };
}
