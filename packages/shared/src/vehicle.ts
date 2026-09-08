export type AppraisalMode = "quick" | "detailed";

export type SellerType = "private" | "dealer" | "unknown";

/** Crawl-enabled marketplaces (seed/probe today). */
export const ALLOWED_SOURCES = [
  "sauto",
  "bazos",
  "tipcars",
  "autobazar_eu",
  "mobile_de",
  "autoscout24",
] as const;

/**
 * Known marketplace slugs including reserved future adapters
 * (TipCars, Autobazar.eu, …). Facebook is intentionally absent.
 */
export const KNOWN_SOURCES = [
  "sauto",
  "bazos",
  "tipcars",
  "autobazar_eu",
  "mobile_de",
  "autoscout24",
  "olx_pl",
] as const;

export type ListingSource = (typeof KNOWN_SOURCES)[number];
export type EnabledListingSource = (typeof ALLOWED_SOURCES)[number];

/** Domestic CZ portals — default firm-estimate / comps pool. */
export const CZ_LISTING_SOURCES = [
  "sauto",
  "bazos",
  "tipcars",
  "autobazar_eu",
] as const satisfies readonly ListingSource[];

/** Import / foreign portals — optional comps toggle; stricter crawl budgets. */
export const IMPORT_LISTING_SOURCES = [
  "mobile_de",
  "autoscout24",
  "olx_pl",
] as const satisfies readonly ListingSource[];

export type CzListingSource = (typeof CZ_LISTING_SOURCES)[number];
export type ImportListingSource = (typeof IMPORT_LISTING_SOURCES)[number];

export const SOURCE_LABELS_CS: Record<ListingSource, string> = {
  sauto: "Sauto",
  bazos: "Bazoš",
  tipcars: "TipCars",
  autobazar_eu: "Autobazar.eu",
  mobile_de: "Mobile.de",
  autoscout24: "AutoScout24",
  olx_pl: "OLX.pl",
};

export const VEHICLE_CATEGORIES = [
  "passenger",
  "van",
  "caravan",
  "motorcycle",
] as const;
export type VehicleCategory = (typeof VEHICLE_CATEGORIES)[number];

export const VEHICLE_CATEGORY_LABELS_CS: Record<VehicleCategory, string> = {
  passenger: "Osobní",
  van: "Dodávka",
  caravan: "Karavan / obytný",
  motorcycle: "Motocykl",
};

export type Tier1Vehicle = {
  category?: VehicleCategory | "other";
  make: string;
  model: string;
  year: number;
  mileageKm: number;
  fuel: string;
  transmission: string;
  body: string;
  motorization?: string;
  powerKw?: number;
  displacementCc?: number;
  catalogVariantId?: string;
  catalogEscape?: boolean;
  catalogEscapeNote?: string;
};

export type Tier2Vehicle = Tier1Vehicle & {
  generation?: string;
  trim?: string;
  drive?: string;
  condition?: string;
  region?: string;
  featureKeys?: string[];
};
