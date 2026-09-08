"""Existence probe — certify that DB-active listings still exist on the source.

Discover (seed) finds inventory. Probe marks gone rows as status=removed.
Never treat transport errors / 429 / 5xx as gone.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from drivecheck_crawler.config import CrawlerConfig, get_config
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.repository import ListingRepository
from drivecheck_crawler.sources import delay_for, resolve_probe_sources

logger = logging.getLogger(__name__)

SAUTO_ITEM = "https://www.sauto.cz/api/v1/items/{item_id}"
SAUTO_REFERER = "https://www.sauto.cz/"

_BAZOS_GONE_TITLE = re.compile(
    r"neexistuje|inzer[aá]t\s+byl\s+ukon|inzer[aá]t\s+nen[ií]|odstraněn",
    re.I,
)

_TIPCARS_GONE_TITLE = re.compile(
    r"neexistuje|nenalezen|nen[ií]\s+k\s+dispozici|inzer[aá]t\s+byl\s+ukon|"
    r"inzer[aá]t\s+nen[ií]|odstraněn|stránka\s+neexistuje",
    re.I,
)

_AUTOBAZAR_GONE_TITLE = re.compile(
    r"neexistuje|nenalezen|nebyla\s+nalezena|nen[ií]\s+k\s+dispozici|"
    r"inzer[aá]t\s+byl\s+ukon|inzer[aá]t\s+nen[ií]|odstraněn|"
    r"stránka\s+neexistuje|404",
    re.I,
)

_DE_GONE_TITLE = re.compile(
    r"nicht\s+gefunden|seite\s+nicht\s+gefunden|anzeige\s+nicht\s+mehr|"
    r"inserat\s+nicht\s+mehr|gel[oö]scht|nicht\s+verf[uü]gbar|"
    r"no\s+longer\s+available|page\s+not\s+found|404",
    re.I,
)


class ProbeVerdict(str, Enum):
    LIVE = "live"
    GONE = "gone"
    UNCERTAIN = "uncertain"


@dataclass
class ProbeStats:
    checked: int = 0
    live: int = 0
    gone: int = 0
    uncertain: int = 0
    marked_removed: int = 0
    touched_live: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, source: str, verdict: ProbeVerdict) -> None:
        self.checked += 1
        bucket = self.by_source.setdefault(
            source, {"checked": 0, "live": 0, "gone": 0, "uncertain": 0}
        )
        bucket["checked"] += 1
        if verdict is ProbeVerdict.LIVE:
            self.live += 1
            bucket["live"] += 1
        elif verdict is ProbeVerdict.GONE:
            self.gone += 1
            bucket["gone"] += 1
        else:
            self.uncertain += 1
            bucket["uncertain"] += 1


def classify_http_status(status_code: int) -> ProbeVerdict:
    if status_code == 200:
        return ProbeVerdict.LIVE
    if status_code in (404, 410):
        return ProbeVerdict.GONE
    if status_code in (429, 500, 502, 503, 504):
        return ProbeVerdict.UNCERTAIN
    # Other 4xx (401/403) — do not mark removed; may be block/WAF.
    if 400 <= status_code < 500:
        return ProbeVerdict.UNCERTAIN
    return ProbeVerdict.UNCERTAIN


# Sauto often keeps item JSON reachable (HTTP 200) after delist — check body.
_SAUTO_GONE_STATUSES = frozenset(
    {
        "deleted",
        "inactive",
        "deactivated",
        "removed",
        "expired",
        "sold",
    }
)


def sauto_item_body_verdict(body: bytes | str | None) -> ProbeVerdict | None:
    """Return GONE/LIVE from Sauto item JSON, or None if status missing/unparseable."""
    if body is None:
        return None
    text = (
        body.decode("utf-8", errors="ignore")
        if isinstance(body, (bytes, bytearray))
        else str(body)
    )
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    item = data.get("result") or data.get("item") or data
    if not isinstance(item, dict):
        return None
    raw = item.get("status")
    if raw is None:
        return None
    status = str(raw).strip().casefold()
    if not status:
        return None
    if status in _SAUTO_GONE_STATUSES:
        return ProbeVerdict.GONE
    if status in {"active", "published", "visible", "edit"}:
        return ProbeVerdict.LIVE
    # Unknown status string — do not invent removals.
    return None


def probe_sauto_item(client: RateLimitedClient, external_id: str) -> ProbeVerdict:
    url = SAUTO_ITEM.format(item_id=external_id)
    try:
        status, body = client.request_raw(
            "GET",
            url,
            headers={"Accept": "application/json", "Referer": SAUTO_REFERER},
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("Sauto probe transport id=%s err=%s", external_id, exc)
        return ProbeVerdict.UNCERTAIN
    http_verdict = classify_http_status(status)
    if http_verdict is not ProbeVerdict.LIVE:
        return http_verdict
    body_verdict = sauto_item_body_verdict(body)
    if body_verdict is not None:
        return body_verdict
    # 200 without a usable status field — treat as live (legacy / sparse payloads).
    return ProbeVerdict.LIVE


def probe_bazos_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
) -> ProbeVerdict:
    if not url:
        return ProbeVerdict.UNCERTAIN
    try:
        status, body = client.request_raw(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://auto.bazos.cz/",
            },
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("Bazos probe transport id=%s err=%s", external_id, exc)
        return ProbeVerdict.UNCERTAIN

    verdict = classify_http_status(status)
    if verdict is not ProbeVerdict.LIVE:
        return verdict

    # Soft-dead pages sometimes still return 200.
    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    if title and _BAZOS_GONE_TITLE.search(title):
        return ProbeVerdict.GONE
    if _BAZOS_GONE_TITLE.search(text[:4000]):
        # Only treat as gone when the phrase appears early (error pages are short).
        if len(text) < 12_000:
            return ProbeVerdict.GONE
    return ProbeVerdict.LIVE


def probe_tipcars_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
) -> ProbeVerdict:
    if not url:
        return ProbeVerdict.UNCERTAIN
    try:
        status, body = client.request_raw(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://www.tipcars.com/",
            },
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("TipCars probe transport id=%s err=%s", external_id, exc)
        return ProbeVerdict.UNCERTAIN

    verdict = classify_http_status(status)
    if verdict is not ProbeVerdict.LIVE:
        return verdict

    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    if title and _TIPCARS_GONE_TITLE.search(title):
        return ProbeVerdict.GONE
    if _TIPCARS_GONE_TITLE.search(text[:4000]) and len(text) < 12_000:
        return ProbeVerdict.GONE
    return ProbeVerdict.LIVE


def probe_autobazar_eu_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
) -> ProbeVerdict:
    if not url:
        return ProbeVerdict.UNCERTAIN
    try:
        status, body = client.request_raw(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://www.autobazar.eu/cs/",
            },
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("Autobazar.eu probe transport id=%s err=%s", external_id, exc)
        return ProbeVerdict.UNCERTAIN

    verdict = classify_http_status(status)
    if verdict is not ProbeVerdict.LIVE:
        return verdict

    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    if title and _AUTOBAZAR_GONE_TITLE.search(title):
        return ProbeVerdict.GONE
    if _AUTOBAZAR_GONE_TITLE.search(text[:4000]) and len(text) < 12_000:
        return ProbeVerdict.GONE
    return ProbeVerdict.LIVE


def _probe_html_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
    referer: str,
    source_label: str,
    gone_title: re.Pattern[str],
) -> ProbeVerdict:
    if not url:
        return ProbeVerdict.UNCERTAIN
    try:
        status, body = client.request_raw(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": referer,
            },
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("%s probe transport id=%s err=%s", source_label, external_id, exc)
        return ProbeVerdict.UNCERTAIN

    verdict = classify_http_status(status)
    if verdict is not ProbeVerdict.LIVE:
        return verdict

    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    head = text[:4000]
    if "Access denied" in head or "Zugriff verweigert" in head:
        return ProbeVerdict.UNCERTAIN

    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    if title and gone_title.search(title):
        return ProbeVerdict.GONE
    if gone_title.search(text[:4000]) and len(text) < 12_000:
        return ProbeVerdict.GONE
    return ProbeVerdict.LIVE


def probe_mobile_de_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
) -> ProbeVerdict:
    return _probe_html_listing(
        client,
        url=url,
        external_id=external_id,
        referer="https://suchen.mobile.de/",
        source_label="Mobile.de",
        gone_title=_DE_GONE_TITLE,
    )


def probe_autoscout24_listing(
    client: RateLimitedClient,
    *,
    url: str,
    external_id: str,
) -> ProbeVerdict:
    return _probe_html_listing(
        client,
        url=url,
        external_id=external_id,
        referer="https://www.autoscout24.de/",
        source_label="AutoScout24",
        gone_title=_DE_GONE_TITLE,
    )


def probe_row(
    client: RateLimitedClient,
    *,
    source: str,
    external_id: str,
    url: str | None,
) -> ProbeVerdict:
    if source == "sauto":
        return probe_sauto_item(client, external_id)
    if source == "bazos":
        return probe_bazos_listing(
            client, url=url or "", external_id=external_id
        )
    if source == "tipcars":
        return probe_tipcars_listing(
            client, url=url or "", external_id=external_id
        )
    if source == "autobazar_eu":
        return probe_autobazar_eu_listing(
            client, url=url or "", external_id=external_id
        )
    if source == "mobile_de":
        return probe_mobile_de_listing(
            client, url=url or "", external_id=external_id
        )
    if source == "autoscout24":
        return probe_autoscout24_listing(
            client, url=url or "", external_id=external_id
        )
    logger.warning("No probe implementation for source=%s", source)
    return ProbeVerdict.UNCERTAIN


def run_probe_actives(
    *,
    source: str = "all",
    limit: int = 500,
    dry_run: bool = True,
    touch_live: bool = True,
    config: CrawlerConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    sources = resolve_probe_sources(source)
    if limit < 1:
        raise ValueError("limit must be >= 1")

    repo = ListingRepository(config.database_url)
    stats = ProbeStats()
    gone_batch: dict[str, list[str]] = {s: [] for s in sources}
    live_batch: dict[str, list[str]] = {s: [] for s in sources}

    with RateLimitedClient(config) as client:
        for src in sources:
            client.set_delay(delay_for(src, config))
            owned_client: RateLimitedClient | None = None
            use_client = client
            if src == "mobile_de":
                from drivecheck_crawler.adapters.mobile_de import build_mobile_de_client

                owned_client = build_mobile_de_client(
                    config, delay_seconds=delay_for(src, config)
                )
                use_client = owned_client
            try:
                # Oldest last_seen first — stale actives are most likely gone.
                rows = repo.list_active_for_probe(source=src, limit=limit)
                logger.info(
                    "Probe source=%s candidates=%s dry_run=%s delay=%s proxy=%s",
                    src,
                    len(rows),
                    dry_run,
                    use_client.delay_seconds,
                    bool(getattr(use_client, "proxy", None)),
                )
                for row in rows:
                    external_id = str(row["external_id"])
                    url = row.get("url")
                    verdict = probe_row(
                        use_client,
                        source=src,
                        external_id=external_id,
                        url=url,
                    )
                    stats.bump(src, verdict)
                    if verdict is ProbeVerdict.GONE:
                        gone_batch[src].append(external_id)
                    elif verdict is ProbeVerdict.LIVE:
                        live_batch[src].append(external_id)

                    if stats.checked % 25 == 0:
                        logger.info(
                            "Probe progress checked=%s live=%s gone=%s uncertain=%s",
                            stats.checked,
                            stats.live,
                            stats.gone,
                            stats.uncertain,
                        )
            finally:
                if owned_client is not None:
                    owned_client.close()

    if not dry_run:
        for src, ids in gone_batch.items():
            n = repo.mark_listings_removed(src, ids)
            stats.marked_removed += n
        if touch_live:
            for src, ids in live_batch.items():
                n = repo.touch_last_seen(src, ids)
                stats.touched_live += n

    result = {
        "dry_run": dry_run,
        "sources": sources,
        "limit_per_source": limit,
        "checked": stats.checked,
        "live": stats.live,
        "gone": stats.gone,
        "uncertain": stats.uncertain,
        "marked_removed": stats.marked_removed,
        "touched_live": stats.touched_live,
        "by_source": stats.by_source,
        "gone_ids_sample": {
            s: ids[:20] for s, ids in gone_batch.items() if ids
        },
    }
    logger.info("Probe finished: %s", result)
    return result
