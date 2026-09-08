ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'passenger';

CREATE TABLE IF NOT EXISTS market_price_daily (
  observed_date DATE NOT NULL,
  category_key TEXT NOT NULL,
  make_key TEXT NOT NULL,
  model_key TEXT NOT NULL,
  year INT NOT NULL,
  dimension_mask SMALLINT NOT NULL CHECK (dimension_mask BETWEEN 0 AND 7),
  fuel_key TEXT NOT NULL DEFAULT '',
  transmission_key TEXT NOT NULL DEFAULT '',
  body_key TEXT NOT NULL DEFAULT '',
  p25_czk INT NOT NULL CHECK (p25_czk > 0),
  median_czk INT NOT NULL CHECK (median_czk > 0),
  p75_czk INT NOT NULL CHECK (p75_czk > 0),
  active_count INT NOT NULL CHECK (active_count > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (
    observed_date, category_key, make_key, model_key, year,
    dimension_mask, fuel_key, transmission_key, body_key
  )
);

CREATE INDEX IF NOT EXISTS market_price_daily_lookup_idx
  ON market_price_daily (
    category_key, make_key, model_key, observed_date DESC, year
  );
