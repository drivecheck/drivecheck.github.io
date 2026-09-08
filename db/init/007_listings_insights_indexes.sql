-- Additive indexes for homepage listings insights aggregations.
-- Safe to re-run; never drops or truncates data.

CREATE INDEX IF NOT EXISTS listings_insights_first_seen_idx
  ON listings (first_seen);

CREATE INDEX IF NOT EXISTS listings_insights_status_source_idx
  ON listings (status, source);

CREATE INDEX IF NOT EXISTS listings_insights_removed_last_seen_idx
  ON listings (last_seen)
  WHERE status = 'removed';

CREATE INDEX IF NOT EXISTS listings_insights_active_make_model_idx
  ON listings (make, model)
  WHERE status = 'active';
