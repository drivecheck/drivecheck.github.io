-- Daily ECB reference rates stored as CZK per 1 unit of foreign currency.
CREATE TABLE IF NOT EXISTS fx_rates (
  quoted_on DATE NOT NULL,
  currency TEXT NOT NULL,
  czk_per_unit NUMERIC(12, 6) NOT NULL CHECK (czk_per_unit > 0),
  source TEXT NOT NULL DEFAULT 'ecb',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (quoted_on, currency)
);

CREATE INDEX IF NOT EXISTS fx_rates_latest_idx ON fx_rates (currency, quoted_on DESC);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_foreign NUMERIC;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS fx_rate_date DATE;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS fx_czk_per_unit NUMERIC;
