"""Fetch ECB daily rates, persist, and re-quote import listings."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from drivecheck_crawler.fx import live_rate_date, live_rates, set_live_rates, to_czk
from drivecheck_crawler.fx_ecb import ECB_DAILY_URL, parse_ecb_daily_xml
from drivecheck_crawler.repository import ListingRepository

logger = logging.getLogger(__name__)

IMPORT_SOURCES = ("mobile_de", "autoscout24", "olx_pl")


def ensure_fx_schema(repo: ListingRepository) -> None:
    with repo.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fx_rates (
                  quoted_on DATE NOT NULL,
                  currency TEXT NOT NULL,
                  czk_per_unit NUMERIC(12, 6) NOT NULL CHECK (czk_per_unit > 0),
                  source TEXT NOT NULL DEFAULT 'ecb',
                  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  PRIMARY KEY (quoted_on, currency)
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_foreign NUMERIC
                """
            )
            cur.execute(
                """
                ALTER TABLE listings ADD COLUMN IF NOT EXISTS fx_rate_date DATE
                """
            )
            cur.execute(
                """
                ALTER TABLE listings ADD COLUMN IF NOT EXISTS fx_czk_per_unit NUMERIC
                """
            )
        conn.commit()


def persist_rates(
    repo: ListingRepository,
    quoted_on: date,
    rates: dict[str, float],
) -> int:
    count = 0
    with repo.connect() as conn:
        with conn.cursor() as cur:
            for currency, czk_per_unit in rates.items():
                if currency == "CZK":
                    continue
                cur.execute(
                    """
                    INSERT INTO fx_rates (quoted_on, currency, czk_per_unit, source)
                    VALUES (%s, %s, %s, 'ecb')
                    ON CONFLICT (quoted_on, currency) DO UPDATE SET
                      czk_per_unit = EXCLUDED.czk_per_unit,
                      fetched_at = now()
                    """,
                    (quoted_on, currency, czk_per_unit),
                )
                count += 1
        conn.commit()
    return count


def load_latest_rates(repo: ListingRepository) -> tuple[date, dict[str, float]] | None:
    with repo.connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT quoted_on, currency, czk_per_unit
                    FROM fx_rates
                    WHERE quoted_on = (SELECT MAX(quoted_on) FROM fx_rates)
                    """
                )
            except Exception:
                return None
            rows = cur.fetchall()
    if not rows:
        return None
    quoted_on = rows[0]["quoted_on"]
    rates = {"CZK": 1.0}
    for row in rows:
        rates[str(row["currency"]).upper()] = float(row["czk_per_unit"])
    return quoted_on, rates


def fetch_ecb_daily(client: httpx.Client | None = None) -> tuple[date, dict[str, float]]:
    own = client is None
    http = client or httpx.Client(timeout=20.0, headers={"User-Agent": "DrivecheckBot/0.2"})
    try:
        response = http.get(ECB_DAILY_URL)
        response.raise_for_status()
        return parse_ecb_daily_xml(response.text)
    finally:
        if own:
            http.close()


def apply_loaded_rates(repo: ListingRepository) -> bool:
    loaded = load_latest_rates(repo)
    if loaded is None:
        return False
    quoted_on, rates = loaded
    set_live_rates(rates, quoted_on)
    return True


def backfill_import_prices(repo: ListingRepository, *, limit: int = 20_000) -> dict[str, int]:
    """Re-quote import rows that stored the original foreign amount."""
    rates = live_rates()
    quoted_on = live_rate_date()
    if not rates or quoted_on is None:
        return {"updated": 0, "skipped": 0}
    updated = 0
    skipped = 0
    with repo.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, currency, price_foreign, price_czk, fx_rate_date
                FROM listings
                WHERE source = ANY(%s)
                  AND currency IS NOT NULL
                  AND upper(currency) <> 'CZK'
                  AND price_foreign IS NOT NULL
                  AND price_foreign > 0
                LIMIT %s
                """,
                (list(IMPORT_SOURCES), limit),
            )
            rows = cur.fetchall()
            for row in rows:
                currency = str(row["currency"])
                if currency.upper() not in rates:
                    skipped += 1
                    continue
                if row["fx_rate_date"] == quoted_on:
                    skipped += 1
                    continue
                try:
                    new_price = to_czk(float(row["price_foreign"]), currency, rates=rates)
                except ValueError:
                    skipped += 1
                    continue
                if new_price == row["price_czk"] and row["fx_rate_date"] == quoted_on:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    UPDATE listings
                    SET price_czk = %s,
                        fx_rate_date = %s,
                        fx_czk_per_unit = %s
                    WHERE id = %s
                    """,
                    (new_price, quoted_on, rates[currency.upper()], row["id"]),
                )
                if new_price != row["price_czk"]:
                    cur.execute(
                        """
                        INSERT INTO price_points (listing_id, price_czk, observed_at)
                        VALUES (%s, %s, %s)
                        """,
                        (row["id"], new_price, datetime.now(timezone.utc)),
                    )
                updated += 1
        conn.commit()
    return {"updated": updated, "skipped": skipped}


def run_fx_sync(
    repo: ListingRepository,
    *,
    fetch: bool = True,
    backfill: bool = True,
) -> dict[str, Any]:
    ensure_fx_schema(repo)
    apply_loaded_rates(repo)
    fetched = False
    quoted_on = live_rate_date()
    today = datetime.now(timezone.utc).date()
    stale = quoted_on is None or quoted_on < today

    if fetch and stale:
        quoted_on, rates = fetch_ecb_daily()
        persist_rates(repo, quoted_on, rates)
        set_live_rates(rates, quoted_on)
        fetched = True
    elif not apply_loaded_rates(repo):
        logger.warning("No ECB rates in fx_rates — using stubs until fx-sync fetch succeeds")

    backfill_result = {"updated": 0, "skipped": 0}
    if backfill and live_rates():
        backfill_result = backfill_import_prices(repo)

    return {
        "fetched": fetched,
        "quoted_on": str(live_rate_date()) if live_rate_date() else None,
        "currencies": sorted((live_rates() or {}).keys()),
        **backfill_result,
    }
