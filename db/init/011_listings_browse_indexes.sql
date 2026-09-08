-- Browse / pulse newest: active listings ordered by first_seen.
-- Safe to re-run; never drops or truncates data.

CREATE INDEX IF NOT EXISTS listings_active_first_seen_idx
  ON listings (first_seen DESC)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS listings_active_published_coalesce_idx
  ON listings ((COALESCE(published_at, first_seen)) DESC)
  WHERE status = 'active';
