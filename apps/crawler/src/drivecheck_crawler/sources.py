"""Marketplace source registry — single place to enable adapters and budgets.

Adding TipCars / Autobazar.eu later should mean registering a SourceDefinition
and an adapter factory — not another if-chain in pipeline/CLI.

Source groups (CLI ``--source``):
- ``all`` — every enabled adapter (CZ↔import interleaved; per-source page budgets)
- ``cz`` — sauto, bazos, tipcars, autobazar_eu
- ``import`` — mobile_de, autoscout24 (, olx_pl when enabled)

Import portals use stricter default page budgets so they cannot starve CZ crawl
(AS24 may override upward; Mobile.de stays low). ``seed --loop`` rotates
**one source per batch** with equal turns (see ``fair_loop_rotation``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from drivecheck_crawler.adapters.base import SourceAdapter
    from drivecheck_crawler.config import CrawlerConfig
    from drivecheck_crawler.cursors import CrawlCursorStore
    from drivecheck_crawler.http_client import RateLimitedClient

AdapterFactory = Callable[
    ["RateLimitedClient", "CrawlerConfig", "CrawlCursorStore"],
    "SourceAdapter",
]

SourceGroup = Literal["cz", "import"]

# Permanently out of scope (drivecheck-design §4.1).
FORBIDDEN_SOURCE_IDS = frozenset(
    {
        "facebook",
        "facebook_marketplace",
        "fb",
        "fb_marketplace",
    }
)

SOURCE_GROUPS: dict[str, frozenset[str]] = {
    "cz": frozenset({"sauto", "bazos", "tipcars", "autobazar_eu"}),
    "import": frozenset({"mobile_de", "autoscout24", "olx_pl"}),
}


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    label_cs: str
    """Crawl + seed enabled today."""
    enabled: bool
    default_currency: str = "CZK"
    """Override global REQUEST_DELAY_SECONDS when set."""
    request_delay_seconds: float | None = None
    supports_probe: bool = False
    adapter_factory: AdapterFactory | None = None
    """Reserved future slug (types/UI) without a live adapter yet."""
    reserved: bool = False
    """Budget group — import sources get smaller default max_pages."""
    group: SourceGroup = "cz"


def _sauto_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.sauto import SautoAdapter

    return SautoAdapter(client, config, cursors)


def _bazos_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.bazos import BazosAdapter

    return BazosAdapter(client, config, cursors)


def _tipcars_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.tipcars import TipCarsAdapter

    return TipCarsAdapter(client, config, cursors)


def _autobazar_eu_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.autobazar_eu import AutobazarEuAdapter

    return AutobazarEuAdapter(client, config, cursors)


def _mobile_de_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.mobile_de import MobileDeAdapter

    return MobileDeAdapter(client, config, cursors)


def _autoscout24_factory(
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    from drivecheck_crawler.adapters.autoscout24 import Autoscout24Adapter

    return Autoscout24Adapter(client, config, cursors)


SOURCES: dict[str, SourceDefinition] = {
    "sauto": SourceDefinition(
        id="sauto",
        label_cs="Sauto",
        enabled=True,
        default_currency="CZK",
        supports_probe=True,
        adapter_factory=_sauto_factory,
        group="cz",
    ),
    # TipCars before Bazoš so fair-loop interleave reaches it before a second
    # Sauto pass (dict order = resolve / rotation order within a group).
    "tipcars": SourceDefinition(
        id="tipcars",
        label_cs="TipCars",
        enabled=True,
        reserved=False,
        default_currency="CZK",
        supports_probe=True,
        adapter_factory=_tipcars_factory,
        group="cz",
    ),
    "bazos": SourceDefinition(
        id="bazos",
        label_cs="Bazoš",
        enabled=True,
        default_currency="CZK",
        supports_probe=True,
        adapter_factory=_bazos_factory,
        group="cz",
    ),
    "autobazar_eu": SourceDefinition(
        id="autobazar_eu",
        label_cs="Autobazar.eu",
        enabled=True,
        reserved=False,
        default_currency="EUR",
        supports_probe=True,
        adapter_factory=_autobazar_eu_factory,
        group="cz",
    ),
    "mobile_de": SourceDefinition(
        id="mobile_de",
        label_cs="Mobile.de",
        enabled=True,
        reserved=False,
        default_currency="EUR",
        supports_probe=True,
        adapter_factory=_mobile_de_factory,
        group="import",
    ),
    "autoscout24": SourceDefinition(
        id="autoscout24",
        label_cs="AutoScout24",
        enabled=True,
        reserved=False,
        default_currency="EUR",
        supports_probe=True,
        adapter_factory=_autoscout24_factory,
        group="import",
    ),
    "olx_pl": SourceDefinition(
        id="olx_pl",
        label_cs="OLX.pl",
        enabled=False,
        default_currency="PLN",
        reserved=True,
        group="import",
    ),
}


def assert_source_allowed(source_id: str) -> None:
    key = source_id.strip().lower()
    if key in FORBIDDEN_SOURCE_IDS:
        raise ValueError(
            f"Source '{source_id}' is permanently out of scope (no Facebook)."
        )


def get_source(source_id: str) -> SourceDefinition:
    assert_source_allowed(source_id)
    key = source_id.strip().lower()
    defn = SOURCES.get(key)
    if defn is None:
        known = ", ".join(sorted(SOURCES))
        raise ValueError(f"Unknown source '{source_id}'. Known: {known}")
    return defn


def enabled_source_ids() -> list[str]:
    return [s.id for s in SOURCES.values() if s.enabled and s.adapter_factory]


def enabled_source_ids_in_group(group: SourceGroup) -> list[str]:
    return [
        s.id
        for s in SOURCES.values()
        if s.enabled and s.adapter_factory and s.group == group
    ]


def probeable_source_ids() -> list[str]:
    return [s.id for s in SOURCES.values() if s.enabled and s.supports_probe]


def known_source_ids() -> list[str]:
    return list(SOURCES.keys())


def _interleave_cz_import(cz: Sequence[str], imports: Sequence[str]) -> list[str]:
    """Zip CZ with import so AutoScout24/Mobile.de are not always last.

    Example: sauto, mobile_de, bazos, autoscout24, tipcars, (remaining CZ…).
    Keeps CZ leading each pair so domestic inventory still runs first.
    """
    out: list[str] = []
    n = max(len(cz), len(imports))
    for i in range(n):
        if i < len(cz):
            out.append(cz[i])
        if i < len(imports):
            out.append(imports[i])
    return out


def fair_loop_rotation(source_ids: Sequence[str]) -> list[str]:
    """Rotation schedule for ``seed --loop``: one source per batch.

    Equal turns for every enabled source (CZ↔import order from
    ``resolve_sources``). Prefer this over serial ``run_seed("all")``, which
    can bury AutoScout24 behind a 30+ minute TipCars/Autobazar marathon.
    """
    return [s for s in source_ids if s]


def resolve_sources(spec: str | Sequence[str]) -> list[str]:
    """Expand CLI ``--source``: ``all`` | ``cz`` | ``import`` | id | comma list."""
    if isinstance(spec, str):
        raw = [p.strip().lower() for p in spec.split(",") if p.strip()]
    else:
        raw = [str(p).strip().lower() for p in spec if str(p).strip()]
    if not raw:
        raise ValueError("No sources specified")
    if raw == ["all"] or (len(raw) == 1 and raw[0] == "all"):
        # Interleave CZ + import so a shared batch/loop cannot bury AutoScout24
        # behind a full Sauto→Bazoš→TipCars→Autobazar marathon.
        return _interleave_cz_import(
            enabled_source_ids_in_group("cz"),
            enabled_source_ids_in_group("import"),
        )
    out: list[str] = []
    for item in raw:
        if item == "all":
            raise ValueError("Cannot mix 'all' with other source ids")
        if item in SOURCE_GROUPS:
            for sid in enabled_source_ids_in_group(item):  # type: ignore[arg-type]
                if sid not in out:
                    out.append(sid)
            continue
        defn = get_source(item)
        if not defn.enabled or defn.adapter_factory is None:
            raise ValueError(
                f"Source '{item}' is registered but not enabled for crawl yet"
            )
        if item not in out:
            out.append(item)
    if not out:
        raise ValueError(f"No enabled sources for spec={spec!r}")
    return out


def resolve_probe_sources(spec: str | Sequence[str]) -> list[str]:
    if isinstance(spec, str):
        raw = [p.strip().lower() for p in spec.split(",") if p.strip()]
    else:
        raw = [str(p).strip().lower() for p in spec if str(p).strip()]
    if not raw or raw == ["all"]:
        return [
            s
            for s in resolve_sources("all")
            if get_source(s).supports_probe
        ]
    out: list[str] = []
    for item in raw:
        if item == "all":
            raise ValueError("Cannot mix 'all' with other source ids")
        if item in SOURCE_GROUPS:
            for sid in enabled_source_ids_in_group(item):  # type: ignore[arg-type]
                if get_source(sid).supports_probe and sid not in out:
                    out.append(sid)
            continue
        defn = get_source(item)
        if not defn.supports_probe:
            raise ValueError(f"Source '{item}' does not support existence probe yet")
        if item not in out:
            out.append(item)
    return out


def delay_for(source_id: str, config: CrawlerConfig) -> float:
    """Env/config override wins, then SourceDefinition, then global delay."""
    override = config.delay_override_for(source_id)
    if override is not None:
        return float(override)
    defn = get_source(source_id)
    if defn.request_delay_seconds is not None:
        return float(defn.request_delay_seconds)
    return float(config.request_delay_seconds)


def max_pages_for(source_id: str, config: CrawlerConfig) -> int:
    """Per-source page budget — import defaults lower than CZ."""
    override = config.max_pages_override_for(source_id)
    if override is not None:
        return max(1, int(override))
    defn = get_source(source_id)
    if defn.group == "import":
        return max(1, int(config.max_pages_import_per_run))
    return max(1, int(config.max_pages_per_run))


def build_adapter(
    source_id: str,
    *,
    client: RateLimitedClient,
    config: CrawlerConfig,
    cursors: CrawlCursorStore,
) -> SourceAdapter:
    defn = get_source(source_id)
    if not defn.enabled or defn.adapter_factory is None:
        raise ValueError(f"No crawl adapter for source '{source_id}'")
    return defn.adapter_factory(client, config, cursors)


def cli_source_choices(*, include_all: bool = True) -> list[str]:
    choices = ["cz", "import", *enabled_source_ids()]
    if include_all:
        return ["all", *choices]
    return choices
