from __future__ import annotations

import logging
from datetime import datetime, timezone

from drivecheck_crawler.config import CrawlerConfig, get_config
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.repository import ListingRepository
from drivecheck_crawler.thumbs.process import image_to_webp_thumb
from drivecheck_crawler.thumbs.storage import LocalFsThumbStorage, ThumbStorage, thumb_key
from drivecheck_crawler.thumbs.urls import (
    download_referer_for_source,
    prepare_download_url,
    resolve_cover_url,
)

logger = logging.getLogger(__name__)

SAUTO_ITEM = "https://www.sauto.cz/api/v1/items/{item_id}"


def _resolve_dto_cover_url(
    dto: ListingDTO,
    *,
    client: RateLimitedClient | None = None,
) -> str | None:
    url = resolve_cover_url(
        source=dto.source,
        external_id=dto.external_id,
        image_url=dto.image_url,
    )
    if url:
        return url
    if dto.source == "sauto" and client is not None:
        return _fetch_sauto_cover(client, dto.external_id, referer=dto.url)
    return None


def _fetch_sauto_cover(
    client: RateLimitedClient, external_id: str, *, referer: str | None
) -> str | None:
    try:
        payload = client.get_json(
            SAUTO_ITEM.format(item_id=external_id),
            referer=referer or "https://www.sauto.cz/",
        )
    except Exception:
        return None
    result = payload.get("result") or {}
    images = result.get("images") or []
    if not images:
        return None
    first = images[0]
    if isinstance(first, dict):
        from drivecheck_crawler.thumbs.urls import absolutize_image_url, is_usable_cover_url

        candidate = absolutize_image_url(first.get("url") if isinstance(first.get("url"), str) else None)
        return candidate if is_usable_cover_url(candidate) else None
    return None


def ensure_listing_thumb(
    repo: ListingRepository,
    dto: ListingDTO,
    *,
    client: RateLimitedClient,
    storage: ThumbStorage,
    config: CrawlerConfig | None = None,
) -> str | None:
    """Download/process cover thumb after upsert. Never raises to caller path."""
    config = config or get_config()
    if not config.thumbs_enabled:
        return None

    source_url = _resolve_dto_cover_url(dto, client=client)
    if not source_url:
        return None

    key = thumb_key(dto.source, dto.external_id)
    try:
        meta = repo.get_thumb_meta(dto.source, dto.external_id)
        if (
            meta
            and meta.get("image_source_url") == source_url
            and meta.get("image_thumb_key") == key
            and storage.exists(key)
        ):
            return key

        download_url = prepare_download_url(source_url)
        referer = download_referer_for_source(dto.source, listing_url=dto.url)
        raw = client.get_bytes(download_url, referer=referer)
        data, digest = image_to_webp_thumb(
            raw,
            max_width=config.thumbs_max_width,
            quality=config.thumbs_webp_quality,
        )
        storage.put(key, data)
        repo.update_thumb_meta(
            dto.source,
            dto.external_id,
            image_source_url=source_url,
            image_thumb_key=key,
            image_thumb_sha256=digest,
        )
        return key
    except Exception:
        logger.warning(
            "Thumb sync failed source=%s id=%s url=%s",
            dto.source,
            dto.external_id,
            source_url,
            exc_info=True,
        )
        return None


def run_thumbs_backfill(
    *,
    limit: int = 100,
    source: str | None = None,
    config: CrawlerConfig | None = None,
) -> dict[str, int]:
    config = config or get_config()
    repo = ListingRepository(config.database_url)
    repo.ensure_thumb_columns()
    storage = LocalFsThumbStorage(config.listing_thumbs_dir)
    stats = {"processed": 0, "ok": 0, "skipped": 0, "errors": 0}
    now = datetime.now(timezone.utc)

    rows = repo.list_listings_needing_thumbs(limit=limit, source=source)
    with RateLimitedClient(config) as client:
        for row in rows:
            stats["processed"] += 1
            dto = ListingDTO(
                source=row["source"],
                external_id=row["external_id"],
                url=row["url"],
                price_czk=int(row["price_czk"]),
                image_url=row.get("image_url"),
                observed_at=row.get("last_seen") or now,
            )
            source_url = _resolve_dto_cover_url(dto, client=client)
            key = thumb_key(dto.source, dto.external_id)
            if (
                source_url
                and row.get("image_source_url") == source_url
                and row.get("image_thumb_key") == key
                and storage.exists(key)
            ):
                stats["skipped"] += 1
                continue
            # Prefer resolved cover so DB image_url gets corrected away from SVG.
            if source_url:
                dto = dto.model_copy(update={"image_url": source_url})
            result = ensure_listing_thumb(
                repo, dto, client=client, storage=storage, config=config
            )
            if result:
                stats["ok"] += 1
            else:
                stats["errors"] += 1

    return stats


def build_thumb_storage(config: CrawlerConfig | None = None) -> LocalFsThumbStorage:
    config = config or get_config()
    return LocalFsThumbStorage(config.listing_thumbs_dir)
