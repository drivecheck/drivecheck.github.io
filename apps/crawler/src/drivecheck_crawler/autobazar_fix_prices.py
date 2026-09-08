"""One-off repair for Autobazar FX poison (fractional EUR mangled via parse_int).

Re-fetches detail HTML for suspect rows and UPDATEs ``price_czk`` / ``currency``.
Never DELETEs. Default threshold 300_000 CZK catches the ~5.5M poison cohort
and milder decimal-strip suspects.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from drivecheck_crawler.adapters.autobazar_eu_extract import (
    detail_record_from_html,
    fields_from_record,
)
from drivecheck_crawler.config import CrawlerConfig, get_config
from drivecheck_crawler.http_client import RateLimitedClient

logger = logging.getLogger(__name__)


def run_autobazar_fix_prices(
    *,
    min_price_czk: int = 300_000,
    limit: int = 200,
    dry_run: bool = True,
    config: CrawlerConfig | None = None,
) -> dict[str, Any]:
    cfg = config or get_config()

    with psycopg.connect(cfg.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_id, url, price_czk, currency
                FROM listings
                WHERE source = 'autobazar_eu'
                  AND status = 'active'
                  AND price_czk >= %s
                ORDER BY price_czk DESC
                LIMIT %s
                """,
                (min_price_czk, limit),
            )
            rows = list(cur.fetchall())

    delay = cfg.request_delay_autobazar_eu or cfg.request_delay_seconds
    client = RateLimitedClient(cfg, delay_seconds=delay)
    checked = 0
    updated = 0
    skipped = 0
    errors = 0
    samples: list[dict[str, Any]] = []

    for external_id, url, old_price, old_currency in rows:
        checked += 1
        try:
            html = client.get_text(str(url))
            record = detail_record_from_html(html)
            if not record:
                skipped += 1
                continue
            if not record.get("id"):
                record = {**record, "id": external_id}
            fields = fields_from_record(record, require_czech=True)
            if not fields:
                skipped += 1
                continue
            new_price = int(fields["price_czk"])
            new_currency = str(fields.get("currency") or "EUR")
            if new_price == int(old_price) and new_currency == str(old_currency or ""):
                skipped += 1
                continue
            sample = {
                "external_id": external_id,
                "old_price_czk": int(old_price),
                "new_price_czk": new_price,
                "old_currency": old_currency,
                "new_currency": new_currency,
            }
            if len(samples) < 8:
                samples.append(sample)
            if dry_run:
                updated += 1
                continue
            with psycopg.connect(cfg.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE listings
                        SET price_czk = %s,
                            currency = %s,
                            last_seen = NOW()
                        WHERE source = 'autobazar_eu'
                          AND external_id = %s
                        """,
                        (new_price, new_currency, external_id),
                    )
                conn.commit()
            updated += 1
        except Exception:
            logger.exception("autobazar fix failed id=%s", external_id)
            errors += 1

    return {
        "dry_run": dry_run,
        "min_price_czk": min_price_czk,
        "checked": checked,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "samples": samples,
    }
