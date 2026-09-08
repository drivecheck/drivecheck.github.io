/** Default ask-to-value haircuts by days on market (CZ used-car negotiation). */

export const DOM_HAIRCUTS = [
  { maxDays: 14, pct: 0.05 },
  { maxDays: 45, pct: 0.08 },
  { maxDays: Number.POSITIVE_INFINITY, pct: 0.12 },
] as const;

export const DEFAULT_ASK_HAIRCUT_PCT = 0.08;

export function haircutPctForDaysOnMarket(days: number | null): number {
  if (days == null || !Number.isFinite(days) || days < 0) {
    return DEFAULT_ASK_HAIRCUT_PCT;
  }
  for (const row of DOM_HAIRCUTS) {
    if (days <= row.maxDays) return row.pct;
  }
  return DOM_HAIRCUTS[DOM_HAIRCUTS.length - 1].pct;
}

export function applyAskHaircut(askCzk: number, daysOnMarket: number | null): number {
  const pct = haircutPctForDaysOnMarket(daysOnMarket);
  return Math.round(askCzk * (1 - pct));
}

/** Ask → reconstructed transaction, with DOM table calibrated by closed sales. */
export function proxyFairValueFromAsk(opts: {
  askCzk: number | null;
  medianDaysOnMarket: number | null;
  soldMedianCzk: number | null;
  closedSalesCount: number;
}): number | null {
  if (opts.askCzk == null || !Number.isFinite(opts.askCzk) || opts.askCzk <= 0) {
    return null;
  }
  const defaultPct = haircutPctForDaysOnMarket(opts.medianDaysOnMarket);
  const pct = calibrateHaircutPct({
    defaultPct,
    askMedianCzk: opts.askCzk,
    soldMedianCzk: opts.soldMedianCzk,
    closedSalesCount: opts.closedSalesCount,
  });
  return Math.round(opts.askCzk * (1 - pct));
}

/**
 * Blend the global haircut toward an empirical gap from closed sales.
 * gapPct = 1 - soldMedian / askMedian (clamped 0–0.25).
 */
export function calibrateHaircutPct(opts: {
  defaultPct: number;
  askMedianCzk: number | null;
  soldMedianCzk: number | null;
  closedSalesCount: number;
}): number {
  const { defaultPct, askMedianCzk, soldMedianCzk, closedSalesCount } = opts;
  if (
    closedSalesCount <= 0 ||
    askMedianCzk == null ||
    soldMedianCzk == null ||
    askMedianCzk <= 0
  ) {
    return defaultPct;
  }
  const raw = 1 - soldMedianCzk / askMedianCzk;
  const empirical = Math.min(0.25, Math.max(0, raw));
  if (closedSalesCount >= 5) return empirical;
  const weight = closedSalesCount / 5;
  return defaultPct * (1 - weight) + empirical * weight;
}
