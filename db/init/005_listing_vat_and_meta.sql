-- VAT / asking-price metadata + useful Sauto detail fields.
-- Idempotent for existing volumes.

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS price_without_vat_czk INTEGER;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS vat_deductible BOOLEAN;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS price_includes_vat BOOLEAN;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS doors INTEGER;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS color TEXT;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS first_owner BOOLEAN;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS service_book BOOLEAN;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS country_of_origin TEXT;

COMMENT ON COLUMN listings.price_czk IS
  'Comparable asking price in CZK including VAT when known (used for market comps).';
COMMENT ON COLUMN listings.price_without_vat_czk IS
  'Seller price excluding VAT when disclosed (dealers / VAT-deductible offers).';
COMMENT ON COLUMN listings.vat_deductible IS
  'True when buyer can reclaim VAT (Sauto price_is_vat_deductible).';
COMMENT ON COLUMN listings.price_includes_vat IS
  'True when the source listed price already included VAT; false when source was excl. VAT.';
