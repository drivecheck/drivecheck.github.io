import type { ListingQuery, ListingRow, ListingStore, PricePointRow } from "@drivecheck/pricing";
import type { ListingSource } from "@drivecheck/shared";
import type { Database } from "sql.js";

function parseFeatures(raw: unknown): string[] | null {
  if (raw == null) return [];
  if (Array.isArray(raw)) return raw.map(String);
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function boolish(value: unknown): boolean | null {
  if (value == null) return null;
  return Boolean(value);
}

function mapRow(row: Record<string, unknown>): ListingRow {
  return {
    id: String(row.id),
    source: row.source as ListingSource,
    external_id: String(row.external_id),
    url: String(row.url),
    make: (row.make as string) ?? null,
    model: (row.model as string) ?? null,
    year: row.year == null ? null : Number(row.year),
    mileage_km: row.mileage_km == null ? null : Number(row.mileage_km),
    price_czk: Number(row.price_czk),
    seller_type: (row.seller_type as ListingRow["seller_type"]) ?? null,
    region: (row.region as string) ?? null,
    fuel: (row.fuel as string) ?? null,
    transmission: (row.transmission as string) ?? null,
    body: (row.body as string) ?? null,
    drive: (row.drive as string) ?? null,
    power_kw: row.power_kw == null ? null : Number(row.power_kw),
    displacement_cc: row.displacement_cc == null ? null : Number(row.displacement_cc),
    feature_keys: parseFeatures(row.feature_keys),
    image_url: null,
    image_thumb_key: null,
    title: (row.title as string) ?? null,
    published_at: (row.published_at as string) ?? null,
    first_seen: (row.first_seen as string) ?? null,
    last_seen: (row.last_seen as string) ?? null,
    status: (row.status as string) ?? "active",
    vat_deductible: boolish(row.vat_deductible),
    price_includes_vat: boolish(row.price_includes_vat),
    currency: (row.currency as string) ?? "CZK",
    price_foreign: row.price_foreign == null ? null : Number(row.price_foreign),
    fx_rate_date: (row.fx_rate_date as string) ?? null,
    color: (row.color as string) ?? null,
  };
}

function allDicts(db: Database, sql: string, params: (string | number)[]): Record<string, unknown>[] {
  const stmt = db.prepare(sql);
  stmt.bind(params);
  const rows: Record<string, unknown>[] = [];
  while (stmt.step()) {
    rows.push(stmt.getAsObject());
  }
  stmt.free();
  return rows;
}

export function catalogMakes(db: Database): string[] {
  return allDicts(
    db,
    `
    SELECT DISTINCT make AS make FROM listings
    WHERE make IS NOT NULL AND trim(make) != ''
    ORDER BY make COLLATE NOCASE
    LIMIT 400
    `,
    [],
  ).map((row) => String(row.make));
}

export function catalogModels(db: Database, make: string): string[] {
  const trimmed = make.trim();
  if (!trimmed) return [];
  return allDicts(
    db,
    `
    SELECT DISTINCT model AS model FROM listings
    WHERE model IS NOT NULL AND trim(model) != ''
      AND make = ?
    ORDER BY model COLLATE NOCASE
    LIMIT 400
    `,
    [trimmed],
  ).map((row) => String(row.model));
}

export function sqliteListingStore(db: Database): ListingStore {
  return {
    async fetchListingRows(query: ListingQuery): Promise<ListingRow[]> {
      const statusPlaceholders = query.statuses.map(() => "?").join(",");
      const params: (string | number)[] = [
        ...query.statuses,
        query.makeNorm,
        query.modelNorm,
        query.yearMin,
        query.yearMax,
        query.limit,
      ];
      const rows = allDicts(
        db,
        `
        SELECT * FROM listings
        WHERE status IN (${statusPlaceholders})
          AND make_norm LIKE '%' || ? || '%'
          AND model_norm LIKE '%' || ? || '%'
          AND (year IS NULL OR (year >= ? AND year <= ?))
        ORDER BY last_seen DESC
        LIMIT ?
        `,
        params,
      );
      return rows.map(mapRow);
    },
    async fetchPricePoints(listingIds: string[]): Promise<PricePointRow[]> {
      if (listingIds.length === 0) return [];
      const placeholders = listingIds.map(() => "?").join(",");
      const rows = allDicts(
        db,
        `SELECT listing_id, price_czk FROM price_points WHERE listing_id IN (${placeholders})`,
        listingIds,
      );
      return rows.map((row) => ({
        listingId: String(row.listing_id),
        priceCzk: Number(row.price_czk),
      }));
    },
    async fetchClosedSales() {
      return [];
    },
    async fetchDomDays(query: ListingQuery, publishedOnly: boolean): Promise<number[]> {
      const sql = publishedOnly
        ? `
          SELECT published_at, first_seen, last_seen FROM listings
          WHERE status = 'active' AND published_at IS NOT NULL
            AND make_norm LIKE '%' || ? || '%'
            AND model_norm LIKE '%' || ? || '%'
            AND (year IS NULL OR (year >= ? AND year <= ?))
          LIMIT 400
        `
        : `
          SELECT published_at, first_seen, last_seen FROM listings
          WHERE status = 'active'
            AND make_norm LIKE '%' || ? || '%'
            AND model_norm LIKE '%' || ? || '%'
            AND (year IS NULL OR (year >= ? AND year <= ?))
          LIMIT 400
        `;
      const rows = allDicts(
        db,
        sql,
        [query.makeNorm, query.modelNorm, query.yearMin, query.yearMax],
      );
      const now = Date.now();
      const out: number[] = [];
      for (const row of rows) {
        const start = Date.parse(String(row.published_at || row.first_seen || ""));
        if (!Number.isFinite(start)) continue;
        out.push((now - start) / 86_400_000);
      }
      return out;
    },
  };
}
