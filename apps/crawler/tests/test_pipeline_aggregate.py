from types import SimpleNamespace

import drivecheck_crawler.pipeline as pipeline


class FakeClient:
    def __init__(self, _config) -> None:
        self.delay_seconds = 1.2

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        pass

    def set_delay(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds


class FakeAdapter:
    source = "sauto"

    def __init__(self, items) -> None:
        self.items = items

    def iter_listings(self, *, max_pages):
        yield from self.items


class FakeRepository:
    def __init__(self) -> None:
        self.upserted = []

    def upsert_listing(self, dto) -> None:
        self.upserted.append(dto)

    def counts(self):
        return {"listings": len(self.upserted), "price_points": 0, "market_price_daily": 0}


def configure(monkeypatch, items):
    repo = FakeRepository()
    adapter = FakeAdapter(items)
    monkeypatch.setattr(pipeline, "ListingRepository", lambda _url: repo)
    monkeypatch.setattr(pipeline, "RateLimitedClient", FakeClient)
    monkeypatch.setattr(pipeline, "CrawlCursorStore", lambda _url: object())
    monkeypatch.setattr(
        pipeline,
        "CrawlHealthStore",
        lambda _url: SimpleNamespace(record_batch=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        pipeline,
        "build_adapter",
        lambda source_id, **_kwargs: adapter,
    )
    monkeypatch.setattr(pipeline, "delay_for", lambda *_args: 1.2)
    monkeypatch.setattr(pipeline, "resolve_sources", lambda _spec: ["sauto"])
    monkeypatch.setattr(pipeline, "enabled_source_ids", lambda: ["sauto", "bazos"])
    monkeypatch.setattr(
        "drivecheck_crawler.fx_sync.run_fx_sync",
        lambda *_args, **_kwargs: {"fetched": False},
    )
    return repo


def _seed_config() -> SimpleNamespace:
    return SimpleNamespace(
        database_url="postgresql://test",
        redis_url="redis://test",
        max_pages_per_run=1,
        thumbs_enabled=False,
        listing_thumbs_dir="data/listing-thumbs",
        max_pages_override_for=lambda _source_id: None,
    )


def test_aggregates_once_after_an_ingesting_batch(monkeypatch) -> None:
    dto = SimpleNamespace(
        external_id="1",
        make="Škoda",
        model="Octavia",
        title="Škoda Octavia",
        feature_keys=[],
        price_czk=250_000,
    )
    repo = configure(monkeypatch, [dto])
    calls = []
    monkeypatch.setattr(
        pipeline,
        "record_daily_market_aggregates",
        lambda used_repo, observed_at: calls.append((used_repo, observed_at)) or 8,
    )
    config = _seed_config()

    result = pipeline.run_seed("sauto", config=config)

    assert result["sauto"] == 1
    assert len(calls) == 1
    assert calls[0][0] is repo


def test_skips_aggregation_when_nothing_was_ingested(monkeypatch) -> None:
    configure(monkeypatch, [])
    calls = []
    monkeypatch.setattr(
        pipeline,
        "record_daily_market_aggregates",
        lambda *_args: calls.append(True) or 0,
    )
    config = _seed_config()

    pipeline.run_seed("sauto", config=config)
    assert calls == []
