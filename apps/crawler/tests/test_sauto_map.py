from drivecheck_crawler.adapters.sauto import SautoAdapter
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import now_utc


class DummyCursor:
    def get(self, key):
        return {}

    def set(self, key, value):
        return None


def _adapter(*, fetch_details: bool = False) -> SautoAdapter:
    return SautoAdapter(
        client=object(),  # type: ignore[arg-type]
        config=CrawlerConfig(sauto_fetch_details=fetch_details),
        cursors=DummyCursor(),  # type: ignore[arg-type]
    )


def test_first_image_url_absolutizes_protocol_relative():
    from drivecheck_crawler.adapters.sauto import _first_image_url

    assert (
        _first_image_url(
            {
                "images": [
                    {"url": "//d19-a.sdn.cz/d_19/c_img_qE_A/example.jpeg"},
                ]
            }
        )
        == "https://d19-a.sdn.cz/d_19/c_img_qE_A/example.jpeg"
    )


def test_map_search_row_skips_pii_and_maps_core_fields():
    adapter = _adapter()
    row = {
        "id": 123,
        "price": 250000,
        "tachometer": 120000,
        "manufacturing_date": "2018-05-01",
        "additional_model_name": "1.6 TDI",
        "manufacturer_cb": {"name": "Škoda", "seo_name": "skoda"},
        "model_cb": {"name": "Octavia", "seo_name": "octavia"},
        "fuel_cb": {"name": "Nafta"},
        "gearbox_cb": {"name": "Manuální"},
        "premise": {"id": 1},
        "locality": {"region": "Středočeský kraj", "street": "Secret 1", "address": "should-not-use"},
        "user": {"id": 9},
        "phone": "123456789",
    }
    dto = adapter._map_search_row(row)
    assert dto is not None
    assert dto.make == "Škoda"
    assert dto.model == "Octavia"
    assert dto.year == 2018
    assert dto.mileage_km == 120000
    assert dto.seller_type == "dealer"
    assert dto.region == "Středočeský kraj"
    assert dto.price_czk == 250000
    # DTO has no phone field by design
    assert not hasattr(dto, "phone")


def test_enrich_from_detail_captures_vat_and_meta_fields():
    class FakeClient:
        def get_json(self, url, referer=None):
            return {
                "result": {
                    "id": 123,
                    "price": 1_239_000,
                    "price_without_vat": 1_023_967,
                    "price_is_without_vat": False,
                    "price_is_vat_deductible": True,
                    "manufacturer_cb": {"name": "Audi"},
                    "model_cb": {"name": "S7"},
                    "additional_model_name": "3.0 TDi DPH",
                    "manufacturing_date": "2021-01-01",
                    "tachometer": 45000,
                    "fuel_cb": {"name": "Nafta"},
                    "gearbox_cb": {"name": "Automatická"},
                    "drive_cb": {"name": "4x4"},
                    "engine_power": 257,
                    "engine_volume": 2967,
                    "vehicle_body_cb": {"name": "Liftback"},
                    "premise": {"id": 1},
                    "locality": {"region": "Praha"},
                    "equipment_cb": [{"name": "Navigace"}],
                    "doors": 5,
                    "color_cb": {"name": "Bílá"},
                    "first_owner": True,
                    "service_book": True,
                    "country_of_origin_cb": {"name": "Česko"},
                    "create_date": "2026-07-01T10:00:00Z",
                }
            }

    adapter = SautoAdapter(
        client=FakeClient(),  # type: ignore[arg-type]
        config=CrawlerConfig(sauto_fetch_details=True),
        cursors=DummyCursor(),  # type: ignore[arg-type]
    )
    base = ListingDTO(
        source="sauto",
        external_id="123",
        url="https://www.sauto.cz/osobni/detail/audi/s7/123",
        price_czk=1_239_000,
        observed_at=now_utc(),
    )
    dto = adapter._enrich_from_detail(base)
    assert dto.price_czk == 1_239_000
    assert dto.price_without_vat_czk == 1_023_967
    assert dto.vat_deductible is True
    assert dto.price_includes_vat is True
    assert dto.doors == 5
    assert dto.color == "Bílá"
    assert dto.first_owner is True
    assert dto.service_book is True
    assert dto.country_of_origin == "Česko"
    assert dto.published_at is not None
    assert "navigation" in dto.feature_keys
