-- Dealer-provided closed sales. VIN is a vehicle identifier the dealer already stores;
-- never store seller name, phone, or email.
CREATE TABLE IF NOT EXISTS closed_sales (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sold_on DATE NOT NULL,
  sold_price_czk INT NOT NULL CHECK (sold_price_czk BETWEEN 5000 AND 50000000),
  vin TEXT,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INT,
  mileage_km INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS closed_sales_segment_idx
  ON closed_sales (make, model, year, sold_on DESC);
