import pytest

from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.sources import (
    FORBIDDEN_SOURCE_IDS,
    assert_source_allowed,
    enabled_source_ids,
    enabled_source_ids_in_group,
    fair_loop_rotation,
    get_source,
    max_pages_for,
    probeable_source_ids,
    resolve_probe_sources,
    resolve_sources,
)


def test_enabled_sources_include_imports():
    assert enabled_source_ids() == [
        "sauto",
        "tipcars",
        "bazos",
        "autobazar_eu",
        "mobile_de",
        "autoscout24",
    ]
    assert set(probeable_source_ids()) == set(enabled_source_ids())


def test_resolve_groups_and_all_interleaves_imports():
    assert resolve_sources("cz") == [
        "sauto",
        "tipcars",
        "bazos",
        "autobazar_eu",
    ]
    assert resolve_sources("import") == ["mobile_de", "autoscout24"]
    # CZ↔import zip — TipCars / AutoScout24 are not buried after full CZ marathon.
    assert resolve_sources("all") == [
        "sauto",
        "mobile_de",
        "tipcars",
        "autoscout24",
        "bazos",
        "autobazar_eu",
    ]
    assert resolve_sources("sauto") == ["sauto"]
    assert resolve_sources("mobile_de,autoscout24") == ["mobile_de", "autoscout24"]


def test_fair_loop_rotation_equal_turns():
    sources = resolve_sources("all")
    rotation = fair_loop_rotation(sources)
    assert rotation == sources
    assert rotation.count("sauto") == 1
    assert "tipcars" in rotation
    assert "autoscout24" in rotation
    # TipCars and AutoScout24 appear before the schedule ends (not only last).
    assert rotation.index("tipcars") < len(rotation) - 1
    assert rotation.index("autoscout24") < len(rotation) - 1


def test_per_source_delay_and_page_defaults():
    from drivecheck_crawler.sources import delay_for

    cfg = CrawlerConfig()
    assert delay_for("sauto", cfg) == 1.0
    assert delay_for("bazos", cfg) == 0.9
    assert delay_for("tipcars", cfg) == 0.8
    assert delay_for("autobazar_eu", cfg) == 0.9
    assert delay_for("autoscout24", cfg) == 1.0
    assert delay_for("mobile_de", cfg) == 2.0
    assert max_pages_for("tipcars", cfg) == 12
    assert max_pages_for("autobazar_eu", cfg) == 12
    assert max_pages_for("autoscout24", cfg) == 4
    assert max_pages_for("mobile_de", cfg) == 2
    assert cfg.tipcars_fetch_details is False
    assert cfg.autobazar_eu_fetch_details is False


def test_import_sources_enabled_and_probeable():
    for sid in ("mobile_de", "autoscout24"):
        defn = get_source(sid)
        assert defn.reserved is False
        assert defn.enabled is True
        assert defn.supports_probe is True
        assert defn.adapter_factory is not None
        assert defn.default_currency == "EUR"
        assert defn.group == "import"


def test_import_page_budget_stricter_than_cz():
    cfg = CrawlerConfig(
        max_pages_per_run=8,
        max_pages_import_per_run=2,
        max_pages_autoscout24=None,
        max_pages_tipcars=None,
        max_pages_autobazar_eu=None,
    )
    assert max_pages_for("sauto", cfg) == 8
    assert max_pages_for("mobile_de", cfg) == 2
    assert max_pages_for("autoscout24", cfg) == 2
    assert enabled_source_ids_in_group("cz")[0] == "sauto"


def test_olx_still_reserved():
    olx = get_source("olx_pl")
    assert olx.reserved is True
    assert olx.enabled is False
    with pytest.raises(ValueError, match="not enabled"):
        resolve_sources("olx_pl")


def test_facebook_forbidden():
    assert "facebook" in FORBIDDEN_SOURCE_IDS
    with pytest.raises(ValueError, match="out of scope"):
        assert_source_allowed("facebook")
    with pytest.raises(ValueError, match="out of scope"):
        get_source("facebook_marketplace")


def test_probe_sources():
    assert resolve_probe_sources("all") == resolve_sources("all")
    assert resolve_probe_sources("cz") == resolve_sources("cz")
    assert resolve_probe_sources("import") == ["mobile_de", "autoscout24"]
    assert resolve_probe_sources("sauto") == ["sauto"]
