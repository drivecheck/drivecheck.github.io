from pathlib import Path

from drivecheck_crawler.adapters.tipcars_extract import (
    fields_from_product,
    find_product,
    list_products_from_html,
    parse_json_ld_blocks,
    parse_max_list_page,
    parse_mileage_km,
    parse_month_year,
)

FIXTURES = Path(__file__).parent / "fixtures" / "tipcars"


def test_list_products_and_max_page():
    html = (FIXTURES / "list_osobni.html").read_text(encoding="utf-8")
    products = list_products_from_html(html)
    assert len(products) == 2
    assert parse_max_list_page(html, page_size=20) == 3308

    fields = fields_from_product(products[0])
    assert fields is not None
    assert fields["external_id"] == "12345678"
    assert fields["price_czk"] == 389_000
    assert fields["region"] == "Brno"
    assert fields["seller_type"] == "dealer"
    assert fields["body"] == "Kombi"
    assert fields["fuel"] == "Nafta"
    assert fields["image_url"] == "https://img.example.invalid/tipcars/octavia-cover.jpg"
    blob = str(fields).casefold()
    assert "777000111" not in blob
    assert "dealer@" not in blob
    assert "ulice" not in blob
    assert "redacted" not in blob
    # Fixture still carries contact noise that must be dropped.
    seller = (products[0].get("offers") or {}).get("seller") or {}
    assert seller.get("telephone")
    assert seller.get("email")


def test_list_products_accepts_dict_shaped_item_list_element():
    """Live TipCars often emits itemListElement as {\"0\": ListItem, …}."""
    html = """
    <script type="application/ld+json">
    {
      "@type": "ItemList",
      "numberOfItems": 2,
      "itemListElement": {
        "1": {
          "@type": "ListItem",
          "position": 2,
          "item": {
            "@type": "Product",
            "@id": "https://www.tipcars.com/vw/golf/vw-golf-87654321.html",
            "name": "Volkswagen Golf",
            "offers": {"@type": "Offer", "price": 250000, "priceCurrency": "CZK"}
          }
        },
        "0": {
          "@type": "ListItem",
          "position": 1,
          "item": {
            "@type": "Product",
            "@id": "https://www.tipcars.com/skoda/fabia/skoda-fabia-12345678.html",
            "name": "Škoda Fabia",
            "offers": {"@type": "Offer", "price": 199000, "priceCurrency": "CZK"}
          }
        }
      }
    }
    </script>
    """
    products = list_products_from_html(html)
    assert len(products) == 2
    # Numeric key order: "0" then "1"
    assert "12345678" in (products[0].get("url") or products[0].get("@id") or "")
    fields = fields_from_product(products[0])
    assert fields is not None
    assert fields["external_id"] == "12345678"
    assert fields["url"].endswith("12345678.html")
    assert fields["price_czk"] == 199_000


def test_detail_fields_year_mileage_power_no_pii():
    html = (FIXTURES / "detail_octavia.html").read_text(encoding="utf-8")
    product = find_product(parse_json_ld_blocks(html))
    assert product is not None
    fields = fields_from_product(product)
    assert fields is not None
    assert fields["make"] == "Škoda"
    assert fields["model"] == "Octavia"
    assert fields["year"] == 2019
    assert fields["mileage_km"] == 148_500
    assert fields["power_kw"] == 110
    assert fields["displacement_cc"] == 1968
    assert fields["transmission"] == "DSG"
    assert fields["drive"] == "Přední"
    assert fields["fuel"] == "Nafta"
    assert fields["region"] == "Brno"

    # VIN / productID and seller contact must never land on commercial fields.
    assert product.get("productID") == "TMBJF7NE5K0123456"
    blob = str(fields).casefold()
    assert "tmbjf7ne5k0123456" not in blob
    assert "777000111" not in blob
    assert "dealer@example.invalid" not in blob
    assert "ulice 12" not in blob
    assert "redacted dealer" not in blob


def test_mileage_rejects_dojezd():
    assert parse_mileage_km("dojezd 450 km WLTP") is None
    assert parse_mileage_km("98 000 km") == 98_000


def test_month_year():
    assert parse_month_year("03/2019") == 2019
    assert parse_month_year("2018") == 2018


def test_detail_without_url_uses_sku_id():
    """Live TipCars detail Product often omits url; sku ends with listing id."""
    product = {
        "@type": "Product",
        "name": "Škoda Kodiaq 2.0 TDI",
        "sku": "35227-36978-0000-11300095",
        "productID": "TMBLJ9NS6P8517498",
        "brand": {"@type": "Brand", "name": "Škoda"},
        "model": "Kodiaq",
        "additionalProperty": [
            {"name": "Typ paliva", "value": "nafta"},
            {"name": "Najeto", "value": "111 637 km"},
            {"name": "Uvedení do provozu", "value": "03/2023"},
            {"name": "Výkon motoru", "value": "110 kW"},
            {"name": "Objem motoru", "value": "1 968 ccm"},
            {"name": "Převodovka", "value": "aut. převodovka"},
            {"name": "Pohon", "value": "pohon 4x4"},
        ],
        "offers": {"@type": "Offer", "price": 648000, "priceCurrency": "CZK"},
    }
    fields = fields_from_product(product)
    assert fields is not None
    assert fields["external_id"] == "11300095"
    assert fields["url"] is None
    assert fields["make"] == "Škoda"
    assert fields["model"] == "Kodiaq"
    assert fields["year"] == 2023
    assert fields["mileage_km"] == 111_637
    assert fields["power_kw"] == 110
    assert fields["displacement_cc"] == 1968
    assert fields["drive"] == "4×4"
    assert "tmb" not in str(fields).casefold()


def test_list_title_make_model_fallback():
    from drivecheck_crawler.adapters.tipcars_extract import make_model_from_title

    assert make_model_from_title("Škoda Kodiaq 2,0 TDI") == ("Škoda", "Kodiaq")
    assert make_model_from_title("Volkswagen Golf 1.5")[0] == "Volkswagen"


def test_first_image_url_absolutizes_protocol_relative_and_path():
    from drivecheck_crawler.adapters.tipcars_extract import first_image_url

    assert (
        first_image_url({"image": "//g.tipcars.com/cover.jpg"})
        == "https://g.tipcars.com/cover.jpg"
    )
    assert (
        first_image_url({"image": "/img/cover.jpg"})
        == "https://www.tipcars.com/img/cover.jpg"
    )
    assert (
        first_image_url(
            {"image": [{"contentUrl": "//g.tipcars.com/from-content.jpg"}]}
        )
        == "https://g.tipcars.com/from-content.jpg"
    )
    assert first_image_url({"image": ""}) is None
