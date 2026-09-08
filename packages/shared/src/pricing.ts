import type {
  AppraisalMode,
  ListingSource,
  SellerType,
  VehicleCategory,
} from "./vehicle";
import type { FeatureValueEstimate } from "./features";

export type ConfidenceLevel = "low" | "medium" | "high";

export type FairValueProvenance = "ask_proxy" | "closed_sales";

export type DealerSettings = {
  marginPct: number;
  reworkBufferCzk: number;
};

export type DealerAdvice = {
  buyInCzk: number | null;
  listAtCzk: number | null;
  commissionCzk: number | null;
  marginPct: number;
  reworkBufferCzk: number;
};

export type CompListing = {
  source: ListingSource;
  externalId: string;
  url: string;
  make: string | null;
  model: string | null;
  year: number | null;
  mileageKm: number | null;
  priceCzk: number;
  sellerType: SellerType | null;
  region: string | null;
  imageUrl?: string | null;
  title?: string | null;
  fuel?: string | null;
  transmission?: string | null;
  body?: string | null;
  drive?: string | null;
  /** Body color when known; public Pages tints the placeholder with it. */
  color?: string | null;
  powerKw?: number | null;
  displacementCc?: number | null;
  featureKeys?: string[];
  publishedAt?: string | null;
  /** Crawl: when Drivecheck first ingested the listing. */
  firstSeenAt?: string | null;
  /** Crawl: last successful observation (or approx. removal time when removed). */
  lastSeenAt?: string | null;
  /** DB listing lifecycle; live offers default to active. */
  listingStatus?: "active" | "removed";
  origin?: "db" | "live";
  listingId?: string;
  vatDeductible?: boolean | null;
  priceIncludesVat?: boolean | null;
  /** Listing currency before FX; priceCzk is always CZK. */
  currency?: string | null;
  /** Original ask in `currency` (import rows). */
  priceForeign?: number | null;
  /** ECB quote date used for priceCzk when currency is not CZK. */
  fxRateDate?: string | null;
};

export type MarketOffer = CompListing & {
  origin: "db" | "live";
};

export type MarketListMode = "db" | "live" | "both";

export type SellerSplit = {
  privateMedianCzk: number | null;
  dealerMedianCzk: number | null;
  privateCount: number;
  dealerCount: number;
};

export type LiquidityStats = {
  sampleSize: number;
  medianDaysOnMarket: number | null;
  noteCs: string;
};

export type SourceSearchLinks = {
  sautoUrl: string;
  bazosUrl: string;
};

export type AppraisalResult = {
  mode: AppraisalMode;
  sampleSize: number;
  priceLowCzk: number | null;
  priceTypicalCzk: number | null;
  priceHighCzk: number | null;
  /** Reconstructed likely transaction. Alias of fairValueCzk for one release. */
  adjustedTypicalCzk: number | null;
  fairValueCzk: number | null;
  fairValueProvenance: FairValueProvenance;
  closedSalesCount: number;
  soldProxyCount: number;
  liveAskCount: number;
  askToValueGapPct: number | null;
  dealerAdvice: DealerAdvice | null;
  confidence: ConfidenceLevel;
  confidenceNoteCs: string;
  sellerSplit: SellerSplit;
  features: FeatureValueEstimate[];
  comps: CompListing[];
  warningsCs: string[];
  liquidity: LiquidityStats;
  sourceLinks: SourceSearchLinks;
};

export type AppraisalRequest = {
  mode: AppraisalMode;
  category?: VehicleCategory | "other";
  make: string;
  model: string;
  year: number;
  mileageKm: number;
  fuel?: string;
  transmission?: string;
  body?: string;
  motorization?: string;
  powerKw?: number;
  displacementCc?: number;
  catalogVariantId?: string;
  catalogEscape?: boolean;
  catalogEscapeNote?: string;
  drive?: string;
  region?: string;
  featureKeys?: string[];
  marginPct?: number;
  reworkBufferCzk?: number;
};

export type HistoryRangePreset = "day" | "week" | "month" | "year" | "custom";
export type PriceHistoryGranularity = "daily" | "weekly" | "monthly";

export type PriceHistoryRequest = Pick<
  AppraisalRequest,
  "mode" | "category" | "make" | "model" | "year" | "fuel" | "transmission" | "body"
> & {
  range: HistoryRangePreset;
  startDate?: string;
  endDate?: string;
};

export type PriceHistoryPoint = {
  date: string;
  p25Czk: number;
  medianCzk: number;
  p75Czk: number;
  sampleSize: number;
};

export type PriceHistoryMetadata = {
  range: HistoryRangePreset;
  startDate: string;
  endDate: string;
  granularity: PriceHistoryGranularity;
  yearWindow: 2 | 6;
  yearWindowWidened: boolean;
  filtersApplied: {
    fuel?: string;
    transmission?: string;
    body?: string;
  };
  warningsCs: string[];
};

export type PriceHistoryResponse = {
  points: PriceHistoryPoint[];
  metadata: PriceHistoryMetadata;
};
