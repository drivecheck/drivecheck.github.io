-- Cover thumbnail metadata (additive; never wipe listings).
ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS image_source_url TEXT;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS image_thumb_key TEXT;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS image_thumb_sha256 TEXT;

CREATE INDEX IF NOT EXISTS listings_thumb_pending_idx
  ON listings (source, external_id)
  WHERE image_url IS NOT NULL
    AND image_thumb_key IS NULL;
