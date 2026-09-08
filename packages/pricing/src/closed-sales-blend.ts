import type { FairValueProvenance } from "@drivecheck/shared";
import { median, roundToThousand } from "./stats";

export const CLOSED_SALES_MIN_FOR_OVERRIDE = 5;

export type ClosedSaleRow = {
  soldPriceCzk: number;
  year: number | null;
  mileageKm: number | null;
};

export function blendFairValueWithClosedSales(opts: {
  proxyCzk: number | null;
  sales: ClosedSaleRow[];
}): {
  fairValueCzk: number | null;
  provenance: FairValueProvenance;
  closedSalesCount: number;
  soldMedianCzk: number | null;
} {
  const prices = opts.sales
    .map((s) => s.soldPriceCzk)
    .filter((n) => Number.isFinite(n) && n > 0);
  const soldMedianCzk = median(prices);
  const closedSalesCount = prices.length;
  const roundedSold =
    soldMedianCzk != null ? roundToThousand(soldMedianCzk) : null;

  if (closedSalesCount >= CLOSED_SALES_MIN_FOR_OVERRIDE && roundedSold != null) {
    return {
      fairValueCzk: roundedSold,
      provenance: "closed_sales",
      closedSalesCount,
      soldMedianCzk: roundedSold,
    };
  }

  if (closedSalesCount > 0 && roundedSold != null && opts.proxyCzk != null) {
    const soldWeight = closedSalesCount / CLOSED_SALES_MIN_FOR_OVERRIDE;
    const mixed = roundToThousand(
      opts.proxyCzk * (1 - soldWeight) + roundedSold * soldWeight,
    );
    return {
      fairValueCzk: mixed,
      provenance: "ask_proxy",
      closedSalesCount,
      soldMedianCzk: roundedSold,
    };
  }

  return {
    fairValueCzk: opts.proxyCzk,
    provenance: "ask_proxy",
    closedSalesCount,
    soldMedianCzk: roundedSold,
  };
}
