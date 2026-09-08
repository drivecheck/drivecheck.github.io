from pathlib import Path

from drivecheck_crawler.adapters.de_normalize import map_de_make
from drivecheck_crawler.adapters.mobile_de_extract import (
    fields_from_record,
    list_records_from_html,
    parse_max_list_page,
)
from drivecheck_crawler.features import normalize_known_feature_list
from drivecheck_crawler.fx import to_czk

FIXTURES = Path(__file__).parent / "fixtures" / "mobile_de"


def test_list_extract_and_accident_skip():
    html = (FIXTURES / "list_de.html").read_text(encoding="utf-8")
    records = list_records_from_html(html)
    assert len(records) == 2
    assert parse_max_list_page(html) == 50

    fields = [fields_from_record(r) for r in records]
    ok = [f for f in fields if f is not None]
    assert len(ok) == 1

    f = ok[0]
    assert f["external_id"] == "371234567"
    assert f["make"] == "Škoda"
    assert f["model"] == "Octavia"
    assert f["year"] == 2019
    assert f["mileage_km"] == 98_000
    assert f["fuel"] == "Nafta"
    assert f["transmission"] == "Manuální"
    assert f["body"] == "Kombi"
    assert f["seller_type"] == "dealer"
    assert f["region"] == "München"
    assert f["currency"] == "EUR"
    assert f["price_czk"] == to_czk(15_500, "EUR")
    assert f["price_czk"] % 100 == 0
    assert f["image_url"] == "https://img.classistatic.de/example/octavia.webp"
    assert "heated_seats" in f["feature_keys"]
    assert "navigation" in f["feature_keys"]
    assert "panorama" in f["feature_keys"]
    # Unknown junk must not be slug-stored
    assert "abs" in f["feature_keys"] or "esp" in f["feature_keys"]
    blob = str(f).casefold()
    assert "telefon" not in blob
    assert "@" not in blob


def test_make_map_skoda():
    assert map_de_make("Skoda") == "Škoda"


def test_known_features_skip_junk():
    keys = normalize_known_feature_list(
        ["Sitzheizung", "Komplett ausgeschlachtet XYZ", "Navigationssystem"]
    )
    assert keys == ["heated_seats", "navigation"]


def test_image_url_absolutizes_protocol_relative():
    base = {
        "id": 371999001,
        "url": "https://suchen.mobile.de/fahrzeuge/details.html?id=371999001",
        "price": {"gross": 12_000, "currency": "EUR"},
        "make": "Skoda",
        "model": "Fabia",
        "firstRegistration": "2018-01",
        "mileage": 90_000,
        "fuel": "PETROL",
        "isAccidentDamaged": False,
        "images": [{"uri": "//img.classistatic.de/api/v1/mo-prod/images/ab/cover.webp"}],
    }
    fields = fields_from_record(base)
    assert fields is not None
    assert (
        fields["image_url"]
        == "https://img.classistatic.de/api/v1/mo-prod/images/ab/cover.webp"
    )
