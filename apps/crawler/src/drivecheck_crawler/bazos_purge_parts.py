"""Soft-hide existing Bazos parts/leasing rows (status=removed). Never DELETE/TRUNCATE."""

from __future__ import annotations

import logging

from drivecheck_crawler.config import CrawlerConfig, get_config
from drivecheck_crawler.listing_quality import should_reject_listing
from drivecheck_crawler.repository import ListingRepository

logger = logging.getLogger(__name__)


def run_bazos_purge_parts(
    *,
    dry_run: bool = True,
    limit: int = 50_000,
    config: CrawlerConfig | None = None,
) -> dict[str, int | bool]:
    config = config or get_config()
    repo = ListingRepository(config.database_url)
    rows = repo.list_active_bazos_for_parts_scan(limit=limit)

    matched: list[tuple[str, str, str | None]] = []
    for row in rows:
        title = row.get("title")
        price = row.get("price_czk")
        url = row.get("url")
        reject = should_reject_listing(
            title=title if isinstance(title, str) else None,
            price_czk=int(price) if isinstance(price, int) else None,
            url=url if isinstance(url, str) else None,
        )
        if reject is None:
            continue
        external_id = str(row["external_id"])
        matched.append((external_id, reject.reason, title if isinstance(title, str) else None))

    for external_id, reason, title in matched[:50]:
        logger.info(
            "bazos purge candidate id=%s reason=%s title=%r dry_run=%s",
            external_id,
            reason,
            (title or "")[:100],
            dry_run,
        )
    if len(matched) > 50:
        logger.info("bazos purge … %s more candidates", len(matched) - 50)

    removed = 0
    if not dry_run and matched:
        removed = repo.mark_listings_removed("bazos", [m[0] for m in matched])

    result = {
        "scanned": len(rows),
        "matched": len(matched),
        "removed": removed,
        "dry_run": dry_run,
    }
    logger.info("bazos purge parts: %s", result)
    return result
