import type { ListingSource } from "@drivecheck/shared";

export type ListingRow = {
  id?: string;
  source: ListingSource;
  external_id: string;
  url: string;
  make: string | null;
  model: string | null;
  year: number | null;
  mileage_km: number | null;
  price_czk: number;
  seller_type: "private" | "dealer" | "unknown" | null;
  region: string | null;
  fuel: string | null;
  transmission: string | null;
  body: string | null;
  drive: string | null;
  power_kw: number | null;
  displacement_cc?: number | null;
  feature_keys: string[] | null;
  image_url: string | null;
  image_thumb_key: string | null;
  title: string | null;
  published_at: Date | string | null;
  first_seen: Date | string | null;
  last_seen: Date | string | null;
  status: string | null;
  vat_deductible: boolean | null;
  price_includes_vat: boolean | null;
  currency: string | null;
  price_foreign: number | null;
  fx_rate_date: Date | string | null;
  color?: string | null;
};

export type ListingStatus = "active" | "removed";

export type ListingQuery = {
  makeNorm: string;
  modelNorm: string;
  yearMin: number;
  yearMax: number;
  statuses: ListingStatus[];
  limit: number;
};

export type PricePointRow = {
  listingId: string;
  priceCzk: number;
};

export type ListingStore = {
  fetchListingRows(query: ListingQuery): Promise<ListingRow[]>;
  fetchPricePoints(listingIds: string[]): Promise<PricePointRow[]>;
  fetchClosedSales(query: ListingQuery): Promise<
    Array<{ soldPriceCzk: number; year: number | null; mileageKm: number | null }>
  >;
  fetchDomDays(query: ListingQuery, publishedOnly: boolean): Promise<number[]>;
};

export function normalizeSearchToken(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

export function listingQueryFromRequest(
  make: string,
  model: string,
  year: number,
  yearWindow: number,
  statuses: ListingStatus[],
  limit = 400,
): ListingQuery {
  return {
    makeNorm: normalizeSearchToken(make),
    modelNorm: normalizeSearchToken(model),
    yearMin: year - yearWindow,
    yearMax: year + yearWindow,
    statuses,
    limit,
  };
}
