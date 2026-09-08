import type { AppraisalRequest, AppraisalResult } from "@drivecheck/shared";
import { blendFairValueWithClosedSales } from "./closed-sales-blend";
import { computeDealerAdvice } from "./dealer-advice";
import { computeFairValueFromComps, rarePositiveFeatureAdj } from "./fair-value";
import { estimateFeatureValues } from "./features";
import { confidenceFromAppraisal } from "./firm-estimate";
import { liquidityFromDomDays } from "./liquidity-from-days";
import { attachHistories, rankComps } from "./rank-comps";
import { selectSoldProxyHistoryCandidates } from "./sold-proxy";
import { buildSourceSearchLinks } from "./source-links";
import { median, roundToThousand } from "./stats";
import {
  listingQueryFromRequest,
  type ListingStore,
} from "./store";

async function loadRanked(
  store: ListingStore,
  input: AppraisalRequest,
  yearWindow: number,
  statuses: Array<"active" | "removed">,
) {
  const rows = await store.fetchListingRows(
    listingQueryFromRequest(input.make, input.model, input.year, yearWindow, statuses),
  );
  return rankComps(rows, input);
}

async function loadLiquidity(
  store: ListingStore,
  input: AppraisalRequest,
  yearWindow: number,
) {
  const q = listingQueryFromRequest(
    input.make,
    input.model,
    input.year,
    yearWindow,
    ["active"],
  );
  const published = await store.fetchDomDays(q, true);
  const usedPublishedOnly = published.length >= 3;
  const days = usedPublishedOnly ? published : await store.fetchDomDays(q, false);
  return liquidityFromDomDays(days, usedPublishedOnly);
}

export async function priceVehicle(
  input: AppraisalRequest,
  store: ListingStore,
): Promise<AppraisalResult> {
  const warningsCs: string[] = [];
  let yearWindow = 2;
  const sourceLinks = buildSourceSearchLinks(input);
  const matchInput: AppraisalRequest = { ...input };

  let [{ comps, rows }, liquidity] = await Promise.all([
    loadRanked(store, matchInput, yearWindow, ["active"]),
    loadLiquidity(store, matchInput, yearWindow),
  ]);

  if (comps.length < 8 && yearWindow < 6) {
    yearWindow = 6;
    const widened = await Promise.all([
      loadRanked(store, matchInput, yearWindow, ["active"]),
      loadLiquidity(store, matchInput, yearWindow),
    ]);
    ({ comps, rows } = widened[0]);
    liquidity = widened[1];
    if (comps.length > 0) {
      warningsCs.push("Málo přesných shod — rozšířen roční filtr (±6 let).");
    }
  }

  const emptySplit = {
    privateMedianCzk: null as number | null,
    dealerMedianCzk: null as number | null,
    privateCount: 0,
    dealerCount: 0,
  };

  const emptyDealer = computeDealerAdvice({
    fairValueCzk: null,
    marginPct: input.marginPct,
    reworkBufferCzk: input.reworkBufferCzk,
  });

  if (comps.length === 0) {
    return {
      mode: input.mode,
      sampleSize: 0,
      priceLowCzk: null,
      priceTypicalCzk: null,
      priceHighCzk: null,
      adjustedTypicalCzk: null,
      fairValueCzk: null,
      fairValueProvenance: "ask_proxy",
      closedSalesCount: 0,
      soldProxyCount: 0,
      liveAskCount: 0,
      askToValueGapPct: null,
      dealerAdvice: emptyDealer,
      confidence: "low",
      confidenceNoteCs:
        "Nenašli jsme srovnatelné inzeráty. Doplňte data crawlem nebo upravte model.",
      sellerSplit: emptySplit,
      features: [],
      comps: [],
      warningsCs,
      liquidity,
      sourceLinks,
    };
  }

  const [removedPack, closedSales] = await Promise.all([
    loadRanked(store, matchInput, yearWindow, ["removed"]),
    store.fetchClosedSales(
      listingQueryFromRequest(input.make, input.model, input.year, yearWindow, [
        "active",
      ]),
    ),
  ]);
  const removedComps = removedPack.comps;
  const historyCandidates = selectSoldProxyHistoryCandidates(removedComps);
  const ids = historyCandidates
    .map((c) => c.listingId)
    .filter((id): id is string => Boolean(id));
  const points = await store.fetchPricePoints(ids);
  const withHistory = attachHistories(historyCandidates, points);
  const historyById = new Map(
    withHistory
      .filter((comp) => comp.listingId)
      .map((comp) => [comp.listingId as string, comp]),
  );
  const removedWithHistory = removedComps.map((comp) =>
    comp.listingId ? (historyById.get(comp.listingId) ?? comp) : comp,
  );

  const featureKeys = input.featureKeys ?? [];
  const features =
    featureKeys.length > 0
      ? estimateFeatureValues(rows, featureKeys, input.year, input.mileageKm)
      : [];
  const featureAdj = rarePositiveFeatureAdj(features);

  const fv = computeFairValueFromComps({
    active: comps,
    removed: removedWithHistory,
    subjectYear: input.year,
    subjectMileageKm: input.mileageKm,
    featureAdjCzk: featureAdj,
  });

  if (fv.mileageAssumed) {
    warningsCs.push(
      `Nájezd neuveden — použili jsme předpoklad ${fv.effectiveMileageKm.toLocaleString("cs-CZ")} km (~15 tis. km/rok).`,
    );
  } else if (fv.effectiveMileageKm >= 300_000) {
    warningsCs.push(
      "Extrémní nájezd — odhad je silně stlačený dolů a jistota klesá; ověřte stav vozu.",
    );
  }

  const blended = blendFairValueWithClosedSales({
    proxyCzk: fv.fairValueCzk,
    sales: closedSales,
  });
  const fairValueCzk = blended.fairValueCzk;
  const adjustedTypicalCzk = fairValueCzk;

  if (blended.provenance === "closed_sales") {
    warningsCs.unshift(
      `Ověřeno na ${blended.closedSalesCount.toLocaleString("cs-CZ")} reálných prodejích.`,
    );
  }

  const privatePrices = comps.filter((c) => c.sellerType === "private").map((c) => c.priceCzk);
  const dealerPrices = comps.filter((c) => c.sellerType === "dealer").map((c) => c.priceCzk);

  const conf = confidenceFromAppraisal({
    sampleSize: fv.liveAskCount,
    yearWindow,
    priceLowCzk: fv.priceLowCzk,
    priceHighCzk: fv.priceHighCzk,
    priceTypicalCzk: fv.priceTypicalCzk,
    featureCount: features.length,
    featureLowConfidenceCount: features.filter((f) => f.lowConfidence).length,
    mileageAssumed: fv.mileageAssumed,
    extremeMileage: !fv.mileageAssumed && fv.effectiveMileageKm >= 300_000,
    soldProxyCount: fv.soldProxyCount,
  });

  let confidenceNoteCs = conf.noteCs;
  if (blended.provenance === "closed_sales") {
    confidenceNoteCs = `Ověřeno na ${blended.closedSalesCount.toLocaleString("cs-CZ")} reálných prodejích. ${conf.noteCs}`;
  }

  return {
    mode: input.mode,
    sampleSize: fv.liveAskCount,
    priceLowCzk: fv.priceLowCzk,
    priceTypicalCzk: fv.priceTypicalCzk,
    priceHighCzk: fv.priceHighCzk,
    adjustedTypicalCzk,
    fairValueCzk,
    fairValueProvenance: blended.provenance,
    closedSalesCount: blended.closedSalesCount,
    soldProxyCount: fv.soldProxyCount,
    liveAskCount: fv.liveAskCount,
    askToValueGapPct: fv.askToValueGapPct,
    dealerAdvice: computeDealerAdvice({
      fairValueCzk,
      marginPct: input.marginPct,
      reworkBufferCzk: input.reworkBufferCzk,
    }),
    confidence: conf.level,
    confidenceNoteCs,
    sellerSplit: {
      privateMedianCzk: (() => {
        const m = median(privatePrices);
        return m != null ? roundToThousand(m) : null;
      })(),
      dealerMedianCzk: (() => {
        const m = median(dealerPrices);
        return m != null ? roundToThousand(m) : null;
      })(),
      privateCount: privatePrices.length,
      dealerCount: dealerPrices.length,
    },
    features,
    comps: comps.slice(0, 200),
    warningsCs,
    liquidity,
    sourceLinks,
  };
}
