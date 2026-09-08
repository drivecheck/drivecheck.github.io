import type { ListingSource } from "@drivecheck/shared";
import type { ListingQuery, ListingRow, ListingStore, PricePointRow } from "./store";
import { normalizeSearchToken } from "./store";

export type MemoryListing = ListingRow & {
  pricePoints?: number[];
};

function matches(row: ListingRow, q: ListingQuery): boolean {
  const status = row.status === "removed" ? "removed" : "active";
  if (!q.statuses.includes(status)) return false;
  const make = normalizeSearchToken(row.make ?? "");
  const model = normalizeSearchToken(row.model ?? "");
  if (!make.includes(q.makeNorm) || !model.includes(q.modelNorm)) return false;
  if (row.year != null && (row.year < q.yearMin || row.year > q.yearMax)) return false;
  return true;
}

export function memoryListingStore(rows: MemoryListing[]): ListingStore {
  return {
    async fetchListingRows(query: ListingQuery): Promise<ListingRow[]> {
      return rows.filter((row) => matches(row, query)).slice(0, query.limit);
    },
    async fetchPricePoints(listingIds: string[]): Promise<PricePointRow[]> {
      const wanted = new Set(listingIds);
      const points: PricePointRow[] = [];
      for (const row of rows) {
        if (!row.id || !wanted.has(row.id) || !row.pricePoints) continue;
        for (const priceCzk of row.pricePoints) {
          points.push({ listingId: row.id, priceCzk });
        }
      }
      return points;
    },
    async fetchClosedSales() {
      return [];
    },
    async fetchDomDays(query: ListingQuery): Promise<number[]> {
      return rows
        .filter((row) => matches(row, { ...query, statuses: ["active"] }))
        .map(() => 20);
    },
  };
}

export function sampleOctaviaRow(
  index: number,
  extra?: Partial<MemoryListing>,
): MemoryListing {
  const year = 2018 + (index % 3);
  return {
    id: `00000000-0000-0000-0000-${String(index).padStart(12, "0")}`,
    source: "sauto" as ListingSource,
    external_id: `oct-${index}`,
    url: `https://www.sauto.cz/item/${index}`,
    make: "Škoda",
    model: "Octavia",
    year,
    mileage_km: 100_000 + index * 3_000,
    price_czk: 280_000 + index * 5_000,
    seller_type: "dealer",
    region: "Praha",
    fuel: "Nafta",
    transmission: "Manuální",
    body: "Kombi",
    drive: "Přední",
    power_kw: 110,
    feature_keys: [],
    image_url: null,
    image_thumb_key: null,
    title: "Škoda Octavia 2.0 TDI",
    published_at: "2026-01-01T00:00:00.000Z",
    first_seen: "2026-01-01T00:00:00.000Z",
    last_seen: "2026-08-01T00:00:00.000Z",
    status: "active",
    vat_deductible: true,
    price_includes_vat: true,
    currency: "CZK",
    price_foreign: null,
    fx_rate_date: null,
    ...extra,
  };
}
