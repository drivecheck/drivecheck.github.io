import type { CompListing, FeatureValueEstimate } from "@drivecheck/shared";
import { applyAskHaircut, haircutPctForDaysOnMarket } from "./haircuts";
import {
  blendFairValue,
  classifySoldProxy,
  listingDaysOnMarket,
  type PricePoint,
} from "./sold-proxy";
import {
  effectiveSubjectMileageKm,
  median,
  mileageYearAdjustmentCzk,
  percentile,
  removeIqrOutliers,
  roundToThousand,
} from "./stats";
import { inclVatComparable } from "./vat";

export type FairValueComp = CompListing & {
  priceHistory?: PricePoint[];
};

function comparableAsk(comp: FairValueComp): number {
  return inclVatComparable(comp.priceCzk, {
    priceIncludesVat: comp.priceIncludesVat,
    vatDeductible: comp.vatDeductible,
  });
}

function normalizedAsk(comp: FairValueComp, subjectYear: number, subjectMileageKm: number): number {
  const base = comparableAsk(comp);
  return (
    base +
    mileageYearAdjustmentCzk({
      subjectYear,
      subjectMileageKm,
      compYear: comp.year,
      compMileageKm: comp.mileageKm,
      basePriceCzk: base,
    })
  );
}

export function rarePositiveFeatureAdj(features: FeatureValueEstimate[]): number {
  const mids = features
    .filter(
      (f) =>
        f.rarity === "rare" &&
        !f.lowConfidence &&
        f.deltaCzkLow != null &&
        f.deltaCzkHigh != null,
    )
    .map((f) => Math.round(((f.deltaCzkLow as number) + (f.deltaCzkHigh as number)) / 2))
    .filter((d) => d > 0);
  const raw = mids.reduce((a, b) => a + b, 0);
  const cap = 120_000;
  if (Math.abs(raw) <= cap) return raw;
  return Math.sign(raw) * cap;
}

export function computeFairValueFromComps(opts: {
  active: FairValueComp[];
  removed: FairValueComp[];
  subjectYear: number;
  subjectMileageKm: number;
  featureAdjCzk?: number;
  now?: number;
}): {
  fairValueCzk: number | null;
  priceLowCzk: number | null;
  priceHighCzk: number | null;
  priceTypicalCzk: number | null;
  soldProxyCount: number;
  liveAskCount: number;
  askToValueGapPct: number | null;
  mileageAssumed: boolean;
  effectiveMileageKm: number;
} {
  const { mileageKm, assumed } = effectiveSubjectMileageKm(
    opts.subjectMileageKm,
    opts.subjectYear,
  );
  const now = opts.now ?? Date.now();
  const featureAdj = opts.featureAdjCzk ?? 0;

  const activeAsks = opts.active
    .map((c) => comparableAsk(c))
    .filter((n) => Number.isFinite(n) && n > 0);
  const cleanAsks = removeIqrOutliers(activeAsks).sort((a, b) => a - b);
  const priceLowCzk = percentile(cleanAsks, 0.25);
  const priceTypicalCzk = percentile(cleanAsks, 0.5);
  const priceHighCzk = percentile(cleanAsks, 0.75);

  const activeDom = opts.active
    .map((c) =>
      listingDaysOnMarket({
        publishedAt: c.publishedAt,
        firstSeenAt: c.firstSeenAt,
        lastSeenAt: c.lastSeenAt ?? new Date(now).toISOString(),
        now,
      }),
    )
    .filter((d): d is number => d != null);
  const medianActiveDom = median(activeDom);

  const haircutLive = opts.active
    .map((c) => {
      const days = listingDaysOnMarket({
        publishedAt: c.publishedAt,
        firstSeenAt: c.firstSeenAt,
        lastSeenAt: c.lastSeenAt ?? new Date(now).toISOString(),
        now,
      });
      const normalized = normalizedAsk(c, opts.subjectYear, mileageKm);
      return applyAskHaircut(normalized, days);
    })
    .filter((n) => Number.isFinite(n) && n > 0);
  const haircutClean = removeIqrOutliers(haircutLive).sort((a, b) => a - b);
  const haircutLiveMedianCzk = percentile(haircutClean, 0.5);

  const proxies: number[] = [];
  for (const row of opts.removed) {
    const classified = classifySoldProxy(
      {
        priceCzk: comparableAsk(row),
        firstSeenAt: row.firstSeenAt,
        lastSeenAt: row.lastSeenAt,
        publishedAt: row.publishedAt,
        priceHistory: (row.priceHistory ?? []).map((p) => ({
          priceCzk: inclVatComparable(p.priceCzk, {
            priceIncludesVat: row.priceIncludesVat,
            vatDeductible: row.vatDeductible,
          }),
        })),
      },
      medianActiveDom,
      now,
    );
    if (classified.kind === "likely_sold" && classified.proxyCzk != null) {
      proxies.push(
        classified.proxyCzk +
          mileageYearAdjustmentCzk({
            subjectYear: opts.subjectYear,
            subjectMileageKm: mileageKm,
            compYear: row.year,
            compMileageKm: row.mileageKm,
            basePriceCzk: classified.proxyCzk,
          }),
      );
    }
  }
  const soldProxyMedianCzk = median(proxies);

  const blended = blendFairValue({
    haircutLiveMedianCzk:
      haircutLiveMedianCzk != null ? haircutLiveMedianCzk + featureAdj : null,
    soldProxyMedianCzk,
    soldProxyCount: proxies.length,
    rawAskMedianCzk: priceTypicalCzk,
    rawAskP25Czk: priceLowCzk,
  });

  const fairValueCzk = blended.fairValueCzk;
  const askToValueGapPct =
    fairValueCzk != null &&
    priceTypicalCzk != null &&
    fairValueCzk > 0
      ? (priceTypicalCzk - fairValueCzk) / fairValueCzk
      : null;

  return {
    fairValueCzk,
    priceLowCzk: priceLowCzk != null ? roundToThousand(priceLowCzk) : null,
    priceTypicalCzk: priceTypicalCzk != null ? roundToThousand(priceTypicalCzk) : null,
    priceHighCzk: priceHighCzk != null ? roundToThousand(priceHighCzk) : null,
    soldProxyCount: proxies.length,
    liveAskCount: cleanAsks.length,
    askToValueGapPct,
    mileageAssumed: assumed,
    effectiveMileageKm: mileageKm,
  };
}

export { haircutPctForDaysOnMarket };
