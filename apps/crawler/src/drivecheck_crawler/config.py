from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _empty_str_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


class CrawlerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://drivecheck:drivecheck@localhost:5432/drivecheck"
    redis_url: str = "redis://localhost:6379/0"
    user_agent: str = "DrivecheckBot/0.1 (+internal; commercial-listing-fields-only)"
    """Global polite delay; per-source overrides below win when set."""
    request_delay_seconds: float = 1.2
    """Sauto JSON API — slightly below global; still polite."""
    request_delay_sauto: float | None = 1.0
    """Bazoš HTML detail-per-listing — keep near 1s (parts filter needs detail)."""
    request_delay_bazos: float | None = 0.9
    """TipCars list JSON-LD — lighter than full HTML detail crawl."""
    request_delay_tipcars: float | None = 0.8
    request_delay_autobazar_eu: float | None = 0.9
    """Mobile.de Akamai — do not lower; 403 spikes from aggressive pacing."""
    request_delay_mobile_de: float | None = 2.0
    request_delay_autoscout24: float | None = 1.0
    sauto_page_size: int = 40
    sauto_fetch_details: bool = True
    bazos_page_size: int = 20
    tipcars_page_size: int = 20
    """List JSON-LD often has fuel/body; year/km usually need detail.

    Default off for discover throughput; set true for richer comps (slower).
    When true, detail is skipped if year+km+fuel already present on the list row.
    """
    tipcars_fetch_details: bool = False
    autobazar_eu_page_size: int = 20
    """List __NEXT_DATA__ already has year/km/fuel/power for most rows.

    Default off for discover; enable to fill sparse list cards (slower).
    When true, detail is skipped if year+km+fuel already present.
    """
    autobazar_eu_fetch_details: bool = False
    mobile_de_page_size: int = 20
    mobile_de_fetch_details: bool = False
    """Optional HTTP(S) proxy for mobile_de only (Akamai blocks typical CZ/DC IPs).

    Example: ``http://user:pass@de-proxy.example:8080`` or ``socks5://127.0.0.1:1080``.
    Leave unset to fetch direct (usually Access denied → 0 rows).
    """
    mobile_de_http_proxy: str | None = None
    """Optional UA for the dedicated mobile_de HTTP client (browser-like default)."""
    mobile_de_user_agent: str | None = None
    autoscout24_page_size: int = 20
    autoscout24_fetch_details: bool = False
    """Default pages per CZ source when CLI omits --max-pages."""
    max_pages_per_run: int = 8
    """Stricter default for import portals (mobile_de; AS24 often overrides)."""
    max_pages_import_per_run: int = 2
    max_pages_sauto: int | None = None
    max_pages_bazos: int | None = None
    """TipCars/Autobazar list-only pages are cheap — slightly above CZ default."""
    max_pages_tipcars: int | None = 12
    max_pages_autobazar_eu: int | None = 12
    max_pages_mobile_de: int | None = None
    """AS24 SSR list cards are rich; allow more pages than Mobile.de."""
    max_pages_autoscout24: int | None = 4
    http_timeout_seconds: float = 30.0
    listing_thumbs_dir: str = "data/listing-thumbs"
    thumbs_enabled: bool = True
    """When false, seed upserts listings without downloading cover thumbs
    (use ``thumbs-backfill`` / probe path later). Failures never block ingest.
    """
    thumbs_on_discover: bool = True
    thumbs_max_width: int = 480
    thumbs_webp_quality: int = 80
    """Default probe batch size per source (CLI may override)."""
    probe_limit_per_source: int = Field(default=500, ge=1)
    """When seed --loop runs, interleave existence probes after each full rotation."""
    probe_in_seed_loop: bool = True
    """How many actives to probe per interleaved loop pass (one source)."""
    probe_loop_limit: int = Field(default=300, ge=1)

    @field_validator(
        "request_delay_sauto",
        "request_delay_bazos",
        "request_delay_tipcars",
        "request_delay_autobazar_eu",
        "request_delay_mobile_de",
        "request_delay_autoscout24",
        "max_pages_sauto",
        "max_pages_bazos",
        "max_pages_tipcars",
        "max_pages_autobazar_eu",
        "max_pages_mobile_de",
        "max_pages_autoscout24",
        "mobile_de_http_proxy",
        "mobile_de_user_agent",
        mode="before",
    )
    @classmethod
    def _empty_optional(cls, value: object) -> object:
        return _empty_str_to_none(value)

    def http_proxy_for(self, source_id: str) -> str | None:
        """Per-source egress proxy (today: mobile_de only)."""
        if source_id.strip().lower() == "mobile_de":
            return self.mobile_de_http_proxy
        return None

    def delay_override_for(self, source_id: str) -> float | None:
        key = source_id.strip().lower()
        mapping = {
            "sauto": self.request_delay_sauto,
            "bazos": self.request_delay_bazos,
            "tipcars": self.request_delay_tipcars,
            "autobazar_eu": self.request_delay_autobazar_eu,
            "mobile_de": self.request_delay_mobile_de,
            "autoscout24": self.request_delay_autoscout24,
        }
        return mapping.get(key)

    def max_pages_override_for(self, source_id: str) -> int | None:
        key = source_id.strip().lower()
        mapping = {
            "sauto": self.max_pages_sauto,
            "bazos": self.max_pages_bazos,
            "tipcars": self.max_pages_tipcars,
            "autobazar_eu": self.max_pages_autobazar_eu,
            "mobile_de": self.max_pages_mobile_de,
            "autoscout24": self.max_pages_autoscout24,
        }
        return mapping.get(key)


def get_config() -> CrawlerConfig:
    return CrawlerConfig()
