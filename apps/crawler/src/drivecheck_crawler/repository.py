from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from drivecheck_crawler.market_aggregate import DailyMarketAggregate, MarketListingRow
from drivecheck_crawler.models import ListingDTO


UPSERT_SQL = """
INSERT INTO listings (
  source, external_id, url, make, model, generation, trim, year, mileage_km,
  fuel, transmission, drive, power_kw, displacement_cc, body, seller_type,
  region,     price_czk, price_without_vat_czk, vat_deductible, price_includes_vat,
  currency, price_foreign, fx_rate_date, fx_czk_per_unit, feature_keys, status, first_seen, last_seen,
  image_url, title, published_at, category,
  doors, color, first_owner, service_book, country_of_origin
) VALUES (
  %(source)s, %(external_id)s, %(url)s, %(make)s, %(model)s, %(generation)s, %(trim)s,
  %(year)s, %(mileage_km)s, %(fuel)s, %(transmission)s, %(drive)s, %(power_kw)s,
  %(displacement_cc)s, %(body)s, %(seller_type)s, %(region)s, %(price_czk)s,
  %(price_without_vat_czk)s, %(vat_deductible)s, %(price_includes_vat)s,
  %(currency)s, %(price_foreign)s, %(fx_rate_date)s, %(fx_czk_per_unit)s, %(feature_keys)s, 'active', %(observed_at)s, %(observed_at)s,
  %(image_url)s, %(title)s, %(published_at)s, %(category)s,
  %(doors)s, %(color)s, %(first_owner)s, %(service_book)s, %(country_of_origin)s
)
ON CONFLICT (source, external_id) DO UPDATE SET
  url = EXCLUDED.url,
  make = COALESCE(EXCLUDED.make, listings.make),
  model = COALESCE(EXCLUDED.model, listings.model),
  generation = COALESCE(EXCLUDED.generation, listings.generation),
  trim = COALESCE(EXCLUDED.trim, listings.trim),
  year = COALESCE(EXCLUDED.year, listings.year),
  mileage_km = COALESCE(EXCLUDED.mileage_km, listings.mileage_km),
  fuel = COALESCE(EXCLUDED.fuel, listings.fuel),
  transmission = COALESCE(EXCLUDED.transmission, listings.transmission),
  drive = COALESCE(EXCLUDED.drive, listings.drive),
  power_kw = COALESCE(EXCLUDED.power_kw, listings.power_kw),
  displacement_cc = COALESCE(EXCLUDED.displacement_cc, listings.displacement_cc),
  body = COALESCE(EXCLUDED.body, listings.body),
  seller_type = COALESCE(EXCLUDED.seller_type, listings.seller_type),
  region = COALESCE(EXCLUDED.region, listings.region),
  price_czk = EXCLUDED.price_czk,
  price_without_vat_czk = COALESCE(EXCLUDED.price_without_vat_czk, listings.price_without_vat_czk),
  vat_deductible = COALESCE(EXCLUDED.vat_deductible, listings.vat_deductible),
  price_includes_vat = COALESCE(EXCLUDED.price_includes_vat, listings.price_includes_vat),
  currency = EXCLUDED.currency,
  price_foreign = COALESCE(EXCLUDED.price_foreign, listings.price_foreign),
  fx_rate_date = COALESCE(EXCLUDED.fx_rate_date, listings.fx_rate_date),
  fx_czk_per_unit = COALESCE(EXCLUDED.fx_czk_per_unit, listings.fx_czk_per_unit),
  feature_keys = CASE
    WHEN cardinality(EXCLUDED.feature_keys) > 0 THEN EXCLUDED.feature_keys
    ELSE listings.feature_keys
  END,
  image_url = COALESCE(EXCLUDED.image_url, listings.image_url),
  title = COALESCE(EXCLUDED.title, listings.title),
  published_at = COALESCE(EXCLUDED.published_at, listings.published_at),
  category = COALESCE(EXCLUDED.category, listings.category),
  doors = COALESCE(EXCLUDED.doors, listings.doors),
  color = COALESCE(EXCLUDED.color, listings.color),
  first_owner = COALESCE(EXCLUDED.first_owner, listings.first_owner),
  service_book = COALESCE(EXCLUDED.service_book, listings.service_book),
  country_of_origin = COALESCE(EXCLUDED.country_of_origin, listings.country_of_origin),
  status = 'active',
  last_seen = EXCLUDED.last_seen
RETURNING id, (xmax = 0) AS inserted, price_czk
"""

FETCH_ACTIVE_MARKET_ROWS_SQL = """
SELECT category, make, model, year, fuel, transmission, body, price_czk
FROM listings
WHERE status = 'active'
  AND currency = 'CZK'
  AND price_czk BETWEEN 5000 AND 50000000
  AND last_seen >= %s
"""

UPSERT_MARKET_PRICE_DAILY_SQL = """
INSERT INTO market_price_daily (
  observed_date, category_key, make_key, model_key, year, dimension_mask,
  fuel_key, transmission_key, body_key,
  p25_czk, median_czk, p75_czk, active_count
) VALUES (
  %(observed_date)s, %(category_key)s, %(make_key)s, %(model_key)s,
  %(year)s, %(dimension_mask)s, %(fuel_key)s, %(transmission_key)s,
  %(body_key)s, %(p25_czk)s, %(median_czk)s, %(p75_czk)s, %(active_count)s
)
ON CONFLICT (
  observed_date, category_key, make_key, model_key, year,
  dimension_mask, fuel_key, transmission_key, body_key
) DO UPDATE SET
  p25_czk = EXCLUDED.p25_czk,
  median_czk = EXCLUDED.median_czk,
  p75_czk = EXCLUDED.p75_czk,
  active_count = EXCLUDED.active_count,
  updated_at = now()
"""


class ListingRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def upsert_listing(self, dto: ListingDTO) -> None:
        payload = {
            "source": dto.source,
            "external_id": dto.external_id,
            "url": dto.url,
            "make": dto.make,
            "model": dto.model,
            "generation": dto.generation,
            "trim": dto.trim,
            "year": dto.year,
            "mileage_km": dto.mileage_km,
            "fuel": dto.fuel,
            "transmission": dto.transmission,
            "drive": dto.drive,
            "power_kw": dto.power_kw,
            "displacement_cc": dto.displacement_cc,
            "body": dto.body,
            "seller_type": dto.seller_type,
            "region": dto.region,
            "price_czk": dto.price_czk,
            "price_without_vat_czk": dto.price_without_vat_czk,
            "vat_deductible": dto.vat_deductible,
            "price_includes_vat": dto.price_includes_vat,
            "currency": dto.currency,
            "price_foreign": dto.price_foreign,
            "fx_rate_date": dto.fx_rate_date,
            "fx_czk_per_unit": dto.fx_czk_per_unit,
            "feature_keys": dto.feature_keys,
            "image_url": dto.image_url,
            "title": dto.title,
            "published_at": dto.published_at,
            "category": dto.category,
            "doors": dto.doors,
            "color": dto.color,
            "first_owner": dto.first_owner,
            "service_book": dto.service_book,
            "country_of_origin": dto.country_of_origin,
            "observed_at": dto.observed_at,
        }
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, price_czk FROM listings
                    WHERE source = %s AND external_id = %s
                    """,
                    (dto.source, dto.external_id),
                )
                existing = cur.fetchone()
                try:
                    with conn.transaction():
                        cur.execute(UPSERT_SQL, payload)
                except Exception:
                    # Older DBs without image columns — fall back. The
                    # nested `conn.transaction()` above issues a SAVEPOINT
                    # before the primary attempt, so on failure it rolls
                    # back to that savepoint (clearing the aborted
                    # transaction state) before re-raising, leaving the
                    # cursor/connection safe to use for the fallback below.
                    cur.execute(
                        """
                        INSERT INTO listings (
                          source, external_id, url, make, model, generation, trim, year, mileage_km,
                          fuel, transmission, drive, power_kw, displacement_cc, body, seller_type,
                          region, price_czk, currency, feature_keys, status, first_seen, last_seen,
                          category
                        ) VALUES (
                          %(source)s, %(external_id)s, %(url)s, %(make)s, %(model)s, %(generation)s, %(trim)s,
                          %(year)s, %(mileage_km)s, %(fuel)s, %(transmission)s, %(drive)s, %(power_kw)s,
                          %(displacement_cc)s, %(body)s, %(seller_type)s, %(region)s, %(price_czk)s,
                          %(currency)s, %(feature_keys)s, 'active', %(observed_at)s, %(observed_at)s,
                          %(category)s
                        )
                        ON CONFLICT (source, external_id) DO UPDATE SET
                          url = EXCLUDED.url,
                          make = COALESCE(EXCLUDED.make, listings.make),
                          model = COALESCE(EXCLUDED.model, listings.model),
                          price_czk = EXCLUDED.price_czk,
                          category = COALESCE(EXCLUDED.category, listings.category),
                          status = 'active',
                          last_seen = EXCLUDED.last_seen
                        RETURNING id, (xmax = 0) AS inserted, price_czk
                        """,
                        payload,
                    )
                row = cur.fetchone()
                listing_id = row["id"]
                should_record_price = existing is None or existing["price_czk"] != dto.price_czk
                if should_record_price:
                    cur.execute(
                        """
                        INSERT INTO price_points (listing_id, price_czk, observed_at)
                        VALUES (%s, %s, %s)
                        """,
                        (listing_id, dto.price_czk, dto.observed_at),
                    )
                if dto.feature_keys:
                    for key in dto.feature_keys:
                        cur.execute(
                            """
                            INSERT INTO feature_tags (key, label_cs)
                            VALUES (%s, %s)
                            ON CONFLICT (key) DO NOTHING
                            """,
                            (key, key.replace("_", " ")),
                        )
            conn.commit()

    def ensure_thumb_columns(self) -> None:
        """Additive schema for cover thumbs (safe on existing DBs)."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_source_url TEXT"
                )
                cur.execute(
                    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_thumb_key TEXT"
                )
                cur.execute(
                    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_thumb_sha256 TEXT"
                )
            conn.commit()

    def get_thumb_meta(self, source: str, external_id: str) -> dict | None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT image_url, image_source_url, image_thumb_key, image_thumb_sha256
                        FROM listings
                        WHERE source = %s AND external_id = %s
                        """,
                        (source, external_id),
                    )
                except Exception:
                    return None
                return cur.fetchone()

    def update_thumb_meta(
        self,
        source: str,
        external_id: str,
        *,
        image_source_url: str,
        image_thumb_key: str,
        image_thumb_sha256: str,
    ) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE listings
                    SET image_source_url = %s,
                        image_thumb_key = %s,
                        image_thumb_sha256 = %s,
                        image_url = %s
                    WHERE source = %s AND external_id = %s
                    """,
                    (
                        image_source_url,
                        image_thumb_key,
                        image_thumb_sha256,
                        image_source_url,
                        source,
                        external_id,
                    ),
                )
            conn.commit()

    def list_listings_needing_thumbs(
        self, *, limit: int = 100, source: str | None = None
    ) -> list[dict]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                params: list[object] = []
                source_clause = ""
                if source:
                    source_clause = "AND source = %s"
                    params.append(source)
                params.append(limit)
                cur.execute(
                    f"""
                    SELECT source, external_id, url, price_czk, image_url,
                           image_source_url, image_thumb_key, last_seen, first_seen
                    FROM listings
                    WHERE (
                        image_thumb_key IS NULL
                        OR image_source_url ILIKE '%%.svg%%'
                        OR coalesce(image_url, '') ILIKE '%%bazos.svg%%'
                    )
                    AND (
                        -- Need a remote cover, or Bazos (can guess /img/1/… from id).
                        (image_url IS NOT NULL AND btrim(image_url) <> '')
                        OR source = 'bazos'
                    )
                    {source_clause}
                    ORDER BY last_seen DESC NULLS LAST
                    LIMIT %s
                    """,
                    params,
                )
                return list(cur.fetchall())

    def mark_missing_removed(self, source: str, seen_external_ids: set[str], older_than: datetime) -> int:
        """Mark active listings not seen in this full pass as removed (optional)."""
        if not seen_external_ids:
            return 0
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE listings
                    SET status = 'removed'
                    WHERE source = %s
                      AND status = 'active'
                      AND last_seen < %s
                      AND NOT (external_id = ANY(%s))
                    """,
                    (source, older_than.astimezone(timezone.utc), list(seen_external_ids)),
                )
                n = cur.rowcount
            conn.commit()
        return n

    def mark_listings_removed(self, source: str, external_ids: list[str]) -> int:
        """Soft-hide listings (status=removed). Never deletes rows."""
        if not external_ids:
            return 0
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE listings
                    SET status = 'removed'
                    WHERE source = %s
                      AND status = 'active'
                      AND external_id = ANY(%s)
                    """,
                    (source, external_ids),
                )
                n = cur.rowcount
            conn.commit()
        return n

    def list_active_for_probe(self, *, source: str, limit: int = 500) -> list[dict]:
        """Active rows for existence probe — oldest last_seen first."""
        if limit < 1:
            return []
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source, external_id, url, last_seen
                    FROM listings
                    WHERE source = %s
                      AND status = 'active'
                    ORDER BY last_seen ASC NULLS FIRST, external_id ASC
                    LIMIT %s
                    """,
                    (source, limit),
                )
                return list(cur.fetchall())

    def touch_last_seen(self, source: str, external_ids: list[str]) -> int:
        """Refresh last_seen for probe-confirmed live actives (no status change)."""
        if not external_ids:
            return 0
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE listings
                    SET last_seen = now()
                    WHERE source = %s
                      AND status = 'active'
                      AND external_id = ANY(%s)
                    """,
                    (source, external_ids),
                )
                n = cur.rowcount
            conn.commit()
        return n

    def list_active_bazos_for_parts_scan(
        self, *, limit: int = 50_000
    ) -> list[dict]:
        """Active Bazos rows for parts purge (title + price only; body is not stored)."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_id, title, price_czk, url
                    FROM listings
                    WHERE source = 'bazos'
                      AND status = 'active'
                    ORDER BY last_seen DESC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                )
                return list(cur.fetchall())

    def fetch_active_market_rows(
        self, observed_at: datetime, max_age_days: int = 7
    ) -> list[MarketListingRow]:
        threshold = observed_at.astimezone(timezone.utc) - timedelta(days=max_age_days)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(FETCH_ACTIVE_MARKET_ROWS_SQL, (threshold,))
                rows = cur.fetchall()
        return [
            MarketListingRow(
                category=row["category"],
                make=row["make"] or "",
                model=row["model"] or "",
                year=row["year"],
                fuel=row["fuel"],
                transmission=row["transmission"],
                body=row["body"],
                price_czk=row["price_czk"],
            )
            for row in rows
        ]

    def upsert_market_price_daily(self, rows: list[DailyMarketAggregate]) -> None:
        if not rows:
            return
        payloads = [
            {
                "observed_date": row.observed_date,
                "category_key": row.category_key,
                "make_key": row.make_key,
                "model_key": row.model_key,
                "year": row.year,
                "dimension_mask": row.dimension_mask,
                "fuel_key": row.fuel_key,
                "transmission_key": row.transmission_key,
                "body_key": row.body_key,
                "p25_czk": row.p25_czk,
                "median_czk": row.median_czk,
                "p75_czk": row.p75_czk,
                "active_count": row.active_count,
            }
            for row in rows
        ]
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_MARKET_PRICE_DAILY_SQL, payloads)
            conn.commit()

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM listings")
                listings = cur.fetchone()["n"]
                cur.execute("SELECT count(*) AS n FROM price_points")
                price_points = cur.fetchone()["n"]
                cur.execute("SELECT count(*) AS n FROM market_price_daily")
                market_price_daily = cur.fetchone()["n"]
        return {
            "listings": listings,
            "price_points": price_points,
            "market_price_daily": market_price_daily,
        }
