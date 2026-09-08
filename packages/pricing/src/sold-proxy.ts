import { roundToThousand } from "./stats";

const DAY_MS = 86_400_000;
export const WITHDRAWN_MAX_DAYS = 3;
const LONG_STAY_DAYS = 14;
const NO_DROP_HAIRCUT = 0.05;

export type PricePoint = { priceCzk: number };

export type SoldProxyListing = {
  priceCzk: number;
  firstSeenAt?: string | null;
  lastSeenAt?: string | null;
  publishedAt?: string | null;
  priceHistory: PricePoint[];
};

export type SoldProxyKind = "likely_sold" | "withdrawn" | "ignore";

export function listingDaysOnMarket(opts: {
  publishedAt?: string | null;
  firstSeenAt?: string | null;
  lastSeenAt?: string | null;
  now?: number;
}): number | null {
  const startRaw = opts.publishedAt ?? opts.firstSeenAt;
  if (!startRaw) return null;
  const start = Date.parse(startRaw);
  if (!Number.isFinite(start)) return null;
  const end = opts.lastSeenAt
    ? Date.parse(opts.lastSeenAt)
    : (opts.now ?? Date.now());
  if (!Number.isFinite(end) || end < start) return null;
  return Math.floor((end - start) / DAY_MS);
}

function hadDownwardMove(history: PricePoint[], lastAsk: number): boolean {
  if (history.length >= 2) {
    for (let i = 1; i < history.length; i += 1) {
      if (history[i].priceCzk < history[i - 1].priceCzk) return true;
    }
    if (history[history.length - 1].priceCzk < history[0].priceCzk) return true;
  }
  if (history.length === 1 && lastAsk < history[0].priceCzk) return true;
  return false;
}

export function classifySoldProxy(
  listing: SoldProxyListing,
  medianActiveDom: number | null,
  now?: number,
): { kind: SoldProxyKind; proxyCzk: number | null; dropped: boolean } {
  const dropped = hadDownwardMove(listing.priceHistory, listing.priceCzk);
  const days = listingDaysOnMarket({
    publishedAt: listing.publishedAt,
    firstSeenAt: listing.firstSeenAt,
    lastSeenAt: listing.lastSeenAt,
    now,
  });

  if (days != null && days < WITHDRAWN_MAX_DAYS && !dropped) {
    return { kind: "withdrawn", proxyCzk: null, dropped: false };
  }

  const longEnough =
    days != null &&
    (days >= LONG_STAY_DAYS ||
      (medianActiveDom != null && days >= medianActiveDom));

  if (!dropped && !longEnough) {
    return { kind: "ignore", proxyCzk: null, dropped: false };
  }

  const lastAsk =
    listing.priceHistory.length > 0
      ? listing.priceHistory[listing.priceHistory.length - 1].priceCzk
      : listing.priceCzk;
  const proxyCzk = dropped
    ? Math.round(lastAsk)
    : Math.round(lastAsk * (1 - NO_DROP_HAIRCUT));

  return { kind: "likely_sold", proxyCzk, dropped };
}

export const SOLD_PROXY_HISTORY_CAP = 80;

export function selectSoldProxyHistoryCandidates<
  T extends {
    listingId?: string | null;
    publishedAt?: string | null;
    firstSeenAt?: string | null;
    lastSeenAt?: string | null;
  },
>(comps: T[], cap = SOLD_PROXY_HISTORY_CAP): T[] {
  const selected: T[] = [];
  for (const comp of comps) {
    if (!comp.listingId) continue;
    const days = listingDaysOnMarket(comp);
    if (days != null && days < WITHDRAWN_MAX_DAYS) continue;
    selected.push(comp);
    if (selected.length >= cap) break;
  }
  return selected;
}

export function blendFairValue(opts: {
  haircutLiveMedianCzk: number | null;
  soldProxyMedianCzk: number | null;
  soldProxyCount: number;
  rawAskMedianCzk: number | null;
  rawAskP25Czk: number | null;
}): { fairValueCzk: number | null; soldWeight: number } {
  const live = opts.haircutLiveMedianCzk;
  const sold = opts.soldProxyMedianCzk;
  const n = opts.soldProxyCount;

  let soldWeight = 0;
  if (n >= 8) soldWeight = 0.7;
  else if (n >= 3) soldWeight = 0.5;

  let mixed: number | null = null;
  if (soldWeight === 0 || sold == null) {
    mixed = live;
  } else if (live == null) {
    mixed = sold;
  } else {
    mixed = sold * soldWeight + live * (1 - soldWeight);
  }

  if (mixed == null || !Number.isFinite(mixed)) {
    return { fairValueCzk: null, soldWeight };
  }

  if (opts.rawAskMedianCzk != null) {
    mixed = Math.min(mixed, opts.rawAskMedianCzk);
  }
  if (n < 8 && opts.rawAskP25Czk != null) {
    mixed = Math.max(mixed, opts.rawAskP25Czk * 0.7);
  }

  return { fairValueCzk: roundToThousand(mixed), soldWeight };
}
