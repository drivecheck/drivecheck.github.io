from pathlib import Path

from drivecheck_crawler.adapters.tipcars import TipCarsAdapter
from drivecheck_crawler.adapters.tipcars_extract import (
    fields_from_product,
    find_product,
    list_products_from_html,
    parse_json_ld_blocks,
)
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.models import ListingDTO

FIXTURES = Path(__file__).parent / "fixtures" / "tipcars"


class _NoopCursors:
    def get(self, _key: str) -> dict:
        return {}

    def set(self, _key: str, _value: dict) -> None:
        return None


def _adapter(*, fetch_details: bool = False) -> TipCarsAdapter:
    config = CrawlerConfig(
        tipcars_fetch_details=fetch_details,
        tipcars_page_size=20,
    )
    return TipCarsAdapter(client=None, config=config, cursors=_NoopCursors())  # type: ignore[arg-type]


def test_list_product_maps_to_dto_without_pii():
    html = (FIXTURES / "list_osobni.html").read_text(encoding="utf-8")
    product = list_products_from_html(html)[0]
    dto = _adapter()._product_to_dto(product)
    assert isinstance(dto, ListingDTO)
    assert dto.source == "tipcars"
    assert dto.external_id == "12345678"
    assert dto.price_czk == 389_000
    assert dto.seller_type == "dealer"
    assert dto.region == "Brno"
    assert dto.body == "Kombi"

    dumped = dto.model_dump()
    blob = str(dumped).casefold()
    assert "777000111" not in blob
    assert "@" not in blob
    assert "ulice" not in blob
    assert "redacted" not in blob
    for banned in ("phone", "email", "seller_name", "vin", "product_id", "street"):
        assert banned not in dumped


def test_detail_enrich_fields_on_dto():
    html = (FIXTURES / "detail_octavia.html").read_text(encoding="utf-8")
    product = find_product(parse_json_ld_blocks(html))
    assert product is not None
    fields = fields_from_product(product)
    assert fields is not None
    dto = _adapter()._fields_to_dto(fields)
    assert dto.make == "Škoda"
    assert dto.model == "Octavia"
    assert dto.year == 2019
    assert dto.mileage_km == 148_500
    assert dto.power_kw == 110
    assert "TMBJF7NE5K0123456" not in str(dto.model_dump())


def test_skips_detail_when_list_already_complete(monkeypatch):
    from drivecheck_crawler.adapters import tipcars as tipcars_mod

    html = (FIXTURES / "detail_octavia.html").read_text(encoding="utf-8")
    product = find_product(parse_json_ld_blocks(html))
    assert product is not None
    adapter = _adapter(fetch_details=True)
    complete = adapter._fields_to_dto(fields_from_product(product))  # type: ignore[arg-type]
    assert not tipcars_mod._needs_detail_enrich(complete)

    called = {"n": 0}

    def _boom(_dto):
        called["n"] += 1
        raise AssertionError("detail enrich should be skipped")

    monkeypatch.setattr(adapter, "_enrich_from_detail", _boom)
    # Simulate list loop branch: complete row → no enrich call.
    if adapter._config.tipcars_fetch_details and tipcars_mod._needs_detail_enrich(
        complete
    ):
        adapter._enrich_from_detail(complete)
    assert called["n"] == 0
