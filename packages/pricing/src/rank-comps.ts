import type { AppraisalRequest, CompListing } from "@drivecheck/shared";
import { CZ_LISTING_SOURCES } from "@drivecheck/shared";
import { isAccidentOrDamagedListing } from "./accident";
import type { FairValueComp } from "./fair-value";
import { filterAndRankOffersByVehicle, type VehicleMatchSubject } from "./match-vehicle";
import type { ListingRow } from "./store";

function iso(value: Date | string | null | undefined): string | null {
  if (value == null) return null;
  if (value instanceof Date) return value.toISOString();
  const text = String(value);
  return text.length > 0 ? text : null;
}

export function mapListingRowToComp(row: ListingRow): CompListing & { _row: ListingRow } {
  return {
    source: row.source,
    externalId: row.external_id,
    url: row.url,
    make: row.make,
    model: row.model,
    year: row.year,
    mileageKm: row.mileage_km,
    priceCzk: row.price_czk,
    sellerType: row.seller_type,
    region: row.region,
    fuel: row.fuel,
    transmission: row.transmission,
    body: row.body,
    color: row.color ?? null,
    drive: row.drive,
    powerKw: row.power_kw,
    displacementCc: row.displacement_cc ?? null,
    featureKeys: row.feature_keys ?? [],
    imageUrl: row.image_url,
    title: row.title,
    publishedAt: iso(row.published_at) ?? iso(row.last_seen),
    firstSeenAt: iso(row.first_seen),
    lastSeenAt: iso(row.last_seen),
    listingStatus: row.status === "removed" ? "removed" : "active",
    origin: "db",
    listingId: row.id,
    vatDeductible: row.vat_deductible,
    priceIncludesVat: row.price_includes_vat,
    currency: row.currency,
    priceForeign: row.price_foreign == null ? null : Number(row.price_foreign),
    fxRateDate:
      row.fx_rate_date instanceof Date
        ? row.fx_rate_date.toISOString().slice(0, 10)
        : row.fx_rate_date,
    _row: row,
  };
}

export function rankComps(
  rows: ListingRow[],
  input: AppraisalRequest,
): { comps: CompListing[]; rows: ListingRow[] } {
  const cz = new Set<string>(CZ_LISTING_SOURCES);
  const safeRows = rows.filter(
    (row) =>
      cz.has(row.source) &&
      !isAccidentOrDamagedListing({
        title: row.title,
        featureKeys: row.feature_keys,
      }),
  );
  const subject: VehicleMatchSubject = {
    make: input.make,
    model: input.model,
    year: input.year,
    mileageKm: input.mileageKm,
    fuel: input.fuel,
    transmission: input.transmission,
    body: input.body,
    drive: input.drive,
    powerKw: input.powerKw,
    displacementCc: input.displacementCc,
    motorization: input.motorization,
    featureKeys: input.featureKeys,
  };
  const mapped = safeRows.map(mapListingRowToComp);
  const ranked = filterAndRankOffersByVehicle(mapped, subject);
  const comps: CompListing[] = ranked.map((item) => {
    const { matchScore: _matchScore, _row, ...comp } = item;
    void _matchScore;
    void _row;
    return comp;
  });
  return { comps, rows: ranked.map((item) => item._row) };
}

export function attachHistories(
  comps: CompListing[],
  points: Array<{ listingId: string; priceCzk: number }>,
): FairValueComp[] {
  const byId = new Map<string, { priceCzk: number }[]>();
  for (const point of points) {
    const list = byId.get(point.listingId) ?? [];
    list.push({ priceCzk: point.priceCzk });
    byId.set(point.listingId, list);
  }
  return comps.map((comp) => ({
    ...comp,
    priceHistory: comp.listingId ? byId.get(comp.listingId) : undefined,
  }));
}
