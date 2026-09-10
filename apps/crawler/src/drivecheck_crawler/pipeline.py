from __future__ import annotations

import logging
from datetime import datetime, timezone

from drivecheck_crawler.accident import should_skip_accident_listing
from drivecheck_crawler.config import CrawlerConfig, get_config
from drivecheck_crawler.listing_quality import should_reject_listing
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.health import CrawlHealthStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.market_aggregate import record_daily_market_aggregates
from drivecheck_crawler.repository import ListingRepository
from drivecheck_crawler.sources import (
    build_adapter,
    delay_for,
    enabled_source_ids,
    max_pages_for,
    resolve_sources,
)
from drivecheck_crawler.thumbs.storage import LocalFsThumbStorage
from drivecheck_crawler.thumbs.sync import ensure_listing_thumb

logger = logging.getLogger(__name__)


def run_seed(
    source: str = "all",
    *,
    max_pages: int | None = None,
    config: CrawlerConfig | None = None,
) -> dict[str, int]:
    config = config or get_config()
    pages = max_pages if max_pages is not None else config.max_pages_per_run
    repo = ListingRepository(config.database_url)
    try:
        from drivecheck_crawler.fx_sync import run_fx_sync

        fx_result = run_fx_sync(repo, fetch=True, backfill=False)
        logger.info("FX rates: %s", fx_result)
    except Exception:
        logger.exception("ECB FX refresh failed — continuing on last known / stub rates")
    cursors = CrawlCursorStore(config.redis_url)
    health = CrawlHealthStore(config.redis_url)

    source_ids = resolve_sources(source)
    ingested: dict[str, int] = {sid: 0 for sid in enabled_source_ids()}
    ingested["errors"] = 0
    ingested["thumbs"] = 0
    ingested["skipped_accident"] = 0
    ingested["skipped_quality"] = 0

    if config.thumbs_enabled:
        try:
            repo.ensure_thumb_columns()
        except Exception:
            logger.warning("Could not ensure thumb columns", exc_info=True)

    thumb_storage = (
        LocalFsThumbStorage(config.listing_thumbs_dir) if config.thumbs_enabled else None
    )

    with RateLimitedClient(config) as client:
        for source_id in source_ids:
            # Explicit CLI --max-pages wins; otherwise per-source / group budgets
            # so import portals cannot starve Sauto/Bazoš in a shared loop.
            source_pages = (
                pages
                if max_pages is not None
                else max_pages_for(source_id, config)
            )
            client.set_delay(delay_for(source_id, config))
            # mobile_de needs a dedicated client (DE headers + optional proxy)
            # so CZ sources keep DrivecheckBot UA / no shared Akamai cookies.
            owned_client: RateLimitedClient | None = None
            use_client = client
            if source_id == "mobile_de":
                from drivecheck_crawler.adapters.mobile_de import build_mobile_de_client

                owned_client = build_mobile_de_client(
                    config, delay_seconds=delay_for(source_id, config)
                )
                use_client = owned_client
            try:
                adapter = build_adapter(
                    source_id, client=use_client, config=config, cursors=cursors
                )
                source_errors = 0
                source_count = 0
                logger.info(
                    "Starting crawl source=%s max_pages=%s delay=%s proxy=%s",
                    adapter.source,
                    source_pages,
                    use_client.delay_seconds,
                    bool(getattr(use_client, "proxy", None)),
                )
                for dto in adapter.iter_listings(max_pages=source_pages):
                    if should_skip_accident_listing(
                        title=dto.title,
                        feature_keys=dto.feature_keys,
                        text_blobs=[dto.make, dto.model],
                    ):
                        ingested["skipped_accident"] += 1
                        logger.info(
                            "Skip accident/damaged source=%s id=%s title=%s",
                            adapter.source,
                            dto.external_id,
                            (dto.title or "")[:80],
                        )
                        continue
                    quality = should_reject_listing(
                        title=getattr(dto, "title", None),
                        price_czk=getattr(dto, "price_czk", None),
                        year=getattr(dto, "year", None),
                        mileage_km=getattr(dto, "mileage_km", None),
                    )
                    if quality is not None:
                        ingested["skipped_quality"] += 1
                        logger.info(
                            "Skip non-car/lease source=%s id=%s reason=%s title=%s",
                            adapter.source,
                            dto.external_id,
                            quality.reason,
                            (getattr(dto, "title", None) or "")[:80],
                        )
                        try:
                            repo.mark_listings_removed(
                                adapter.source, [str(dto.external_id)]
                            )
                        except Exception:
                            logger.debug(
                                "Could not soft-hide rejected listing source=%s id=%s",
                                adapter.source,
                                dto.external_id,
                                exc_info=True,
                            )
                        continue
                    try:
                        repo.upsert_listing(dto)
                        ingested[adapter.source] = ingested.get(adapter.source, 0) + 1
                        source_count += 1
                        if (
                            thumb_storage is not None
                            and config.thumbs_on_discover
                        ):
                            # Thumb failures never raise; skip via thumbs_on_discover
                            # to keep discover fast on slow CDNs (backfill later).
                            key = ensure_listing_thumb(
                                repo,
                                dto,
                                client=use_client,
                                storage=thumb_storage,
                                config=config,
                            )
                            if key:
                                ingested["thumbs"] += 1
                        if ingested[adapter.source] % 10 == 0:
                            logger.info(
                                "Progress source=%s count=%s last=%s %s %s",
                                adapter.source,
                                ingested[adapter.source],
                                dto.external_id,
                                dto.make,
                                dto.price_czk,
                            )
                    except Exception:
                        ingested["errors"] += 1
                        source_errors += 1
                        logger.exception(
                            "Failed upsert source=%s id=%s",
                            adapter.source,
                            dto.external_id,
                        )
                health.record_batch(
                    adapter.source,
                    ingested=source_count,
                    errors=source_errors,
                )
            finally:
                if owned_client is not None:
                    owned_client.close()

    listings_ingested = sum(
        v
        for k, v in ingested.items()
        if k not in ("errors", "thumbs", "skipped_accident", "skipped_quality")
    )
    if listings_ingested > 0:
        aggregate_count = record_daily_market_aggregates(
            repo, datetime.now(timezone.utc)
        )
        logger.info("Daily market aggregates upserted: %s", aggregate_count)

    logger.info("Seed batch done: %s db=%s", ingested, repo.counts())
    return ingested
