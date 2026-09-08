import type { VehicleCategory } from "./vehicle";

/** Primary source that supplied the richest vehicle attributes. */
export type VinDecodeProvider = "cz-rsv" | "nhtsa" | "wmi" | "paid";

export type VinDecodeSectionId =
  | "identification"
  | "engine"
  | "body"
  | "weights"
  | "emissions"
  | "homologation"
  | "registration"
  | "other";

export type VinDecodeField = {
  key: string;
  labelCs: string;
  /** Raw scalar for tests / consumers. */
  value: string | number | boolean;
  /** Ready-to-show value (units already applied). */
  display: string;
};

export type VinDecodeSection = {
  id: VinDecodeSectionId;
  titleCs: string;
  fields: VinDecodeField[];
};

/**
 * Vehicle-attribute decode only (make/model/year/tech).
 * Not owner history, stolen status, or police databases.
 *
 * Flat core fields stay for appraisal autofill; `sections` carries the full tech card.
 */
export type VinDecodeResult = {
  vin: string;
  make?: string;
  model?: string;
  year?: number;
  fuel?: string;
  body?: string;
  transmission?: string;
  powerKw?: number;
  displacementCc?: number;
  category?: VehicleCategory | "other";
  /** Body color when known (display only; not an appraisal Tier-1 field). */
  color?: string;
  /** ISO date YYYY-MM-DD when known. */
  firstRegistration?: string;
  /** STK validity end date YYYY-MM-DD when known. */
  stkValidTo?: string;
  variant?: string;
  version?: string;
  drive?: string;
  doors?: number;
  seats?: number;
  maxSpeedKmh?: number;
  wmi?: string;
  /** Dense tech-card sections (empty sections omitted). */
  sections: VinDecodeSection[];
  /** Providers that contributed at least one attribute. */
  sources: VinDecodeProvider[];
  provider: VinDecodeProvider;
  notesCs: string[];
  /** False when VIN shape is invalid or no useful attributes were found. */
  ok: boolean;
};

export interface VinLookupProvider {
  readonly name: string;
  lookup(vin: string): Promise<VinDecodeResult>;
}
