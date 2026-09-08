from bs4 import BeautifulSoup

from drivecheck_crawler.adapters.bazos import BazosAdapter
from drivecheck_crawler.adapters.bazos_extract import (
    clean_region,
    extract_body,
    extract_displacement_cc,
    extract_drive,
    extract_fields,
    extract_fuel,
    extract_mileage_km,
    extract_power_kw,
    extract_transmission,
    extract_year,
)


DETAIL_HTML = """
<html><body>
  <h1 class="nadpisdetail">Škoda Octavia 3 Combi 1.4 TSI 110 kW</h1>
  <div class="popisdetail">
    09/2016 | 134 288 km | Benzín | STK 05/2028 | manuální převodovka
  </div>
  <table>
    <tr><td>Jméno:</td><td>Prodejce XY</td></tr>
    <tr><td>Lokalita:</td><td>719 00 Ostrava</td></tr>
    <tr><td>Cena:</td><td>289 000 Kč</td></tr>
  </table>
  <img class="carousel-cell-image"
       data-flickity-lazyload="https://www.bazos.cz/img/1/543/222154543.jpg" />
</body></html>
"""


def test_table_value_accepts_colon_labels():
    soup = BeautifulSoup(DETAIL_HTML, "lxml")
    assert BazosAdapter._table_value(soup, "Cena") == "289 000 Kč"
    assert BazosAdapter._table_value(soup, "Lokalita") == "719 00 Ostrava"


def test_happy_path_labeled_facts():
    text = "Najeto 185 000 km, r.v. 2018, nafta, automat"
    fields = extract_fields(text)
    assert fields.mileage_km == 185_000
    assert fields.year == 2018
    assert fields.fuel == "Nafta"
    assert fields.transmission == "Automatická"


def test_detail_snippet_year_mileage_fuel_transmission_power_body():
    text = (
        "Škoda Octavia 3 Combi 1.4 TSI 110 kW\n"
        "09/2016 | 134 288 km | Benzín | STK 05/2028 | manuální převodovka"
    )
    fields = extract_fields(text)
    assert fields.year == 2016
    assert fields.mileage_km == 134_288
    assert fields.fuel == "Benzín"
    assert fields.transmission == "Manuální"
    assert fields.power_kw == 110
    assert fields.body == "Kombi"
    assert fields.displacement_cc == 1400


def test_mileage_rejects_repair_po_km():
    """Classic trap: service milestone must not become odometer."""
    assert extract_mileage_km("po 8050 km se opravoval motor") is None
    assert extract_mileage_km("Po 8 050km se opravoval motor, jinak OK") is None


def test_mileage_rejects_repair_context_only_po_km_large():
    """Even a large 'po X km' alone must not become mileage."""
    assert extract_mileage_km("po 120 000 km vyměněny rozvody") is None
    assert extract_mileage_km("rozvody v 150000 km, spojka v pořádku") is None
    assert extract_mileage_km("při 90000 km výměna oleje") is None


def test_mileage_prefers_odometer_over_repair_mention():
    text = "Najeto 185 000 km. Po 80 000 km vyměněny rozvody."
    assert extract_mileage_km(text) == 185_000


def test_mileage_tis_km():
    assert extract_mileage_km("nájezd 145 tis. km") == 145_000
    assert extract_mileage_km("Najeto 98 tis km, r.v. 2015") == 98_000
    assert extract_mileage_km("najeto 156 tkm") == 156_000


def test_mileage_rejects_dojezd_range():
    """EV/tank range must not become odometer (Mercedes EQC-style ads)."""
    assert extract_mileage_km("EQC 400, dojezd 1310 km, r.v. 2020") is None
    assert extract_mileage_km("elektrický dojezd 450 km (WLTP)") is None
    assert extract_mileage_km("dojezd až 410 km, WLTP") is None
    assert extract_mileage_km("420 km WLTP, pěkné auto") is None


def test_mileage_prefers_odometer_over_dojezd():
    assert (
        extract_mileage_km(
            "Mercedes-Benz EQC 400, dojezd 1310 km, najeto 184.000 km, r.v. 2020"
        )
        == 184_000
    )
    # Common Bazos trap: najeto without trailing "km", only dojezd has "km".
    assert extract_mileage_km("Najeto 184000, dojezd 1310 km, r.v. 2020") == 184_000
    assert extract_mileage_km("Najeto: 184.000. Dojezd až 410 km.") == 184_000
    assert (
        extract_mileage_km("VW ID.3 dojezd WLTP 420 km / 98000 km") == 98_000
    )


def test_mileage_keeps_labeled_low_odometer():
    """New cars with explicit najeto must keep low readings."""
    assert extract_mileage_km("Škoda Enyaq, najeto 1200 km, skoro nová") == 1_200
    assert extract_mileage_km("BMW iX3, dojezd 460 km, najeto 12 000 km") == 12_000


def test_mileage_km_label_without_trailing_unit():
    assert extract_mileage_km("stav km 156000") == 156_000
    assert extract_mileage_km("stav tachometru 156000") == 156_000
    assert extract_mileage_km("km: 156000, r.v. 2017") == 156_000


def test_year_labeled_and_rejects_stk():
    assert extract_year("r.v. 2018, nafta") == 2018
    assert extract_year("rok výroby 2014") == 2014
    assert extract_year("Passat B8 ročník 2017 nafta") == 2017
    assert extract_year("BMW 320d vyrobeno 2014") == 2014
    # STK date must not win; bare year alone in STK context → null
    assert extract_year("STK do 05/2026, servisní knížka") is None
    assert extract_year("09/2016 | Benzín | STK 05/2028") == 2016


def test_year_ignores_expiry_keeps_car_year():
    assert extract_year("auto z 2019, dálniční známka 2026") == 2019
    assert (
        extract_year("Octavia 2016, najeto 200000 km, platná STK 2027") == 2016
    )


def test_fuel_transmission_power_variants():
    assert extract_fuel("Octavia 2.0 TDI") == "Nafta"
    assert extract_fuel("Enyaq Elektro 150 kW") == "Elektro"
    assert extract_fuel("plug-in hybrid") == "Hybrid"
    assert extract_transmission("DSG převodovka") == "Automatická"
    assert extract_transmission("manuální") == "Manuální"
    assert extract_power_kw("110 kW") == 110
    assert extract_power_kw("150 koní") == 110  # ~110 kW
    # Price must not be read as power
    assert extract_power_kw("Cena 289000 Kč, hezké auto") is None


def test_body_and_drive():
    assert extract_body("Octavia Combi") == "Kombi"
    assert extract_body("SUV sportovní") == "SUV"
    assert extract_body("sedan elegance") == "Sedan"
    assert extract_drive("Audi A4 quattro") == "4x4"
    assert extract_drive("pohon všech kol, zima") == "4x4"
    assert extract_drive("xDrive 20d") == "4x4"
    assert extract_drive("pěkné auto") is None


def test_displacement_requires_engine_token_or_ccm():
    assert extract_displacement_cc("1.4 TSI 110 kW") == 1400
    assert extract_displacement_cc("1968 ccm TDI") == 1968
    # Bare liters without engine family → too weak
    assert extract_displacement_cc("verze 1.4, stav dobrý") is None


def test_region_strips_zip_and_rejects_contact():
    assert clean_region("719 00 Ostrava") == "Ostrava"
    assert clean_region("Mělník") == "Mělník"
    assert clean_region("Ul. Hlavní 12, tel 777123456") is None
    assert clean_region("Ostrava, mobil 602123456") is None
    assert clean_region("jan.novak@email.cz") is None


def test_no_phone_leakage_in_fields():
    text = (
        "Prodám Octavia. Tel: 777 123 456, email prodej@example.com, "
        "bydliště Ulice 5 Praha. Po 8050 km se opravoval motor."
    )
    fields = extract_fields(text)
    assert fields.mileage_km is None
    # Year/phone digits must not become manufacturing year
    assert fields.year is None
    assert clean_region("Praha 5, tel 777123456") is None
    assert clean_region("jan.novak@email.cz") is None


def test_ambiguous_returns_null_rather_than_guess():
    # Multiple bare years without labels → refuse
    assert extract_year("auto 2015 nebo 2016 dle TP") is None
    # Empty / irrelevant
    assert extract_fields("Prodám, volejte").mileage_km is None
    assert extract_fields("Prodám, volejte").year is None
