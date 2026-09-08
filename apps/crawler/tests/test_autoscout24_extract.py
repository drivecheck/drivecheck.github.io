from pathlib import Path

from drivecheck_crawler.adapters.autoscout24_extract import (
    fields_from_record,
    list_records_from_html,
    parse_max_list_page,
)
from drivecheck_crawler.adapters.de_normalize import (
    map_de_fuel,
    map_de_transmission,
)
from drivecheck_crawler.fx import to_czk

FIXTURES = Path(__file__).parent / "fixtures" / "autoscout24"


def test_list_extract_maps_de_to_cz_and_skips_accident():
    html = (FIXTURES / "list_de.html").read_text(encoding="utf-8")
    records = list_records_from_html(html)
    assert len(records) == 3
    assert parse_max_list_page(html) == 200

    fields = [fields_from_record(r) for r in records]
    ok = [f for f in fields if f is not None]
    # One Unfallwagen / isCurrentlyDamaged row dropped
    assert len(ok) == 2

    first = ok[0]
    assert first["external_id"] == "462254974"
    assert first["make"] == "Opel"
    assert first["model"] == "Corsa"
    assert first["fuel"] == "Benzín"
    assert first["transmission"] == "Manuální"
    assert first["currency"] == "EUR"
    assert first["price_czk"] == to_czk(380, "EUR")
    assert first["price_czk"] % 100 == 0
    assert first["region"] == "Berlin"
    blob = str(first).casefold()
    assert "rhinstr" not in blob
    assert "seibold" not in blob
    assert "frank" not in blob


def test_de_fuel_transmission_maps():
    assert map_de_fuel("Benzin") == "Benzín"
    assert map_de_fuel("Diesel") == "Nafta"
    assert map_de_transmission("Schaltgetriebe") == "Manuální"
    assert map_de_transmission("Automatik") == "Automatická"


def test_accident_record_excluded():
    html = (FIXTURES / "list_de.html").read_text(encoding="utf-8")
    damaged = next(
        r
        for r in list_records_from_html(html)
        if (r.get("vehicle") or {}).get("isCurrentlyDamaged")
    )
    assert fields_from_record(damaged) is None


def test_image_url_absolutizes_protocol_relative():
    html = (FIXTURES / "list_de.html").read_text(encoding="utf-8")
    record = list_records_from_html(html)[0]
    record = {
        **record,
        "images": [
            "//prod.pictures.autoscout24.net/listing-images/x.jpg/250x188.webp"
        ],
        "vehicle": {
            **(record.get("vehicle") or {}),
            "isCurrentlyDamaged": False,
            "modelVersionInput": "Klima",
            "subtitle": "OK",
        },
        "specialConditions": [],
        "price": {"priceRaw": 6990},
    }
    fields = fields_from_record(record)
    assert fields is not None
    assert fields["image_url"] == (
        "https://prod.pictures.autoscout24.net/listing-images/x.jpg/250x188.webp"
    )
