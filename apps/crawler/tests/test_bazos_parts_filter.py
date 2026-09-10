"""Bazos parts-vs-vehicle filter: reject parts ads, keep real cars."""

from __future__ import annotations

from bs4 import BeautifulSoup

from drivecheck_crawler.adapters.bazos import BazosAdapter
from drivecheck_crawler.adapters.bazos_parts_filter import (
    is_likely_vehicle_listing,
    should_reject_as_parts,
)


def _reject_reason(title: str, popis: str | None = None, price: int | None = None) -> str | None:
    r = should_reject_as_parts(title, popis, price)
    return r.reason if r else None


# --- Clear parts ads (must reject) ---


def test_reject_nahradni_dily_title():
    assert _reject_reason("Náhradní díly Škoda Octavia 1.9 TDI", price=3500)


def test_reject_dily_na_brand():
    assert _reject_reason("Díly na VW Golf 5 1.9 TDI", price=8000)


def test_reject_motor_na():
    assert _reject_reason("Motor na Škoda Fabia 1.2 HTP", price=12_000)


def test_reject_prodam_motor():
    assert _reject_reason("Prodám motor 1.9 TDI BXE Octavia", price=15_000)


def test_reject_prevodovka_na():
    assert _reject_reason("Převodovka na BMW E90 320d", price=9000)


def test_reject_kapota():
    assert _reject_reason("Prodám kapotu na Audi A4 B8", price=4500)


def test_reject_naraznik():
    assert _reject_reason("Prodám přední nárazník VW Passat B6", price=2500)


def test_reject_zrcatko_svetlomet():
    assert _reject_reason("Prodám zrcátko levé Octavia 3", price=1200)
    assert _reject_reason("Prodám světlomet pravý Golf 7", price=3500)


def test_reject_kola_sada():
    assert _reject_reason("Prodám sadu kol 16\" Škoda", price=6000)
    assert _reject_reason("Prodám zimní pneu 205/55 R16", price=4000)


def test_reject_bazar_dilu_rozborka_vrak():
    assert _reject_reason("Bazar dílů BMW E46", price=500)
    assert _reject_reason("Rozborka Peugeot 307", price=0)
    assert _reject_reason("Škoda Octavia 1.9 TDI na náhradní díly / vrak", price=8000)


def test_reject_na_dily():
    assert _reject_reason("Ford Focus 1.6 na díly", price=5000)


def test_reject_sedacky_volant():
    assert _reject_reason("Prodám sedačky kožené Octavia RS", price=7000)
    assert _reject_reason("Prodám volant s airbagem Golf 6", price=3000)


def test_reject_weak_parts_low_price():
    """Supporting signal: partsy word + very low price, no car-sale cues."""
    assert _reject_reason("Octavia motor", price=9_000)


# --- Real cars (must keep), including service-history language ---


def test_keep_octavia_with_rozvody_service():
    title = "Škoda Octavia 2.0 TDI 110 kW Combi"
    popis = "Najeto 185 000 km. Po 180 tkm vyměněny rozvody, spojka OK."
    assert is_likely_vehicle_listing(title, popis, 289_000)
    assert _reject_reason(title, popis, 289_000) is None


def test_keep_car_vymenene_dily_in_description():
    title = "VW Golf 7 1.4 TSI 92 kW"
    popis = "Pravidelný servis, vyměněny díly brzd, nové spojky, STK do 2027."
    assert _reject_reason(title, popis, 245_000) is None


def test_keep_car_mention_motor_ok():
    title = "BMW 320d xDrive Touring 140 kW"
    popis = "Motor bez vůlí, převodovka výborná, najeto 162000 km."
    assert _reject_reason(title, popis, 420_000) is None


def test_keep_prodam_auto_with_year_mileage():
    title = "Prodám Škoda Fabia 1.0 TSI 70 kW 2019"
    assert _reject_reason(title, "85 000 km, benzín, manuál", 215_000) is None


def test_keep_combi_kw_title():
    title = "Audi A6 Avant 3.0 TDI 160 kW"
    assert _reject_reason(title, None, 350_000) is None


def test_keep_rv_and_km_in_title():
    title = "Hyundai i30 1.6 CRDi r.v. 2017 112000 km"
    assert _reject_reason(title, None, 189_000) is None


def test_keep_nebourane_stk():
    title = "Toyota Corolla 1.8 Hybrid"
    popis = "1. majitel, nebourané, STK 11/2027, serviska"
    assert _reject_reason(title, popis, 399_000) is None


def test_keep_originalni_dily_service_context():
    title = "Mazda 6 2.2 Skyactiv-D 129 kW"
    popis = "Servisováno originálními díly, rozvody vyměněny."
    assert _reject_reason(title, popis, 310_000) is None


# --- Edge cases ---


def test_reject_when_unsure_weak_parts_no_vehicle_cues():
    """User asked: when unsure with a concrete parts token → reject."""
    assert _reject_reason("Blatník Fabia", price=40_000)


def test_empty_title_and_body_not_treated_as_parts():
    # Broken parse must not be classified as parts.
    assert should_reject_as_parts(None, None, 100_000) is None
    assert should_reject_as_parts("", "", 100_000) is None


def test_deep_description_parts_word_does_not_reject_car():
    """Only first line of popis is considered — deep body must not dominate."""
    title = "Renault Megane 1.5 dCi 81 kW Grandtour"
    popis = (
        "Najeto 145000 km, r.v. 2016, výborný stav.\n\n"
        + ("x " * 50)
        + "prodám motor a převodovku zvlášť kdyby zájem"
    )
    # First line is vehicle facts → keep
    assert _reject_reason(title, popis, 175_000) is None


def test_first_line_strong_parts_rejects_even_with_car_price():
    title = "Náhradní díly Octavia"
    popis = "Kompletní rozborka vozu, vše skladem."
    assert _reject_reason(title, popis, 250_000)


def test_tire_size_pattern_rejects():
    assert _reject_reason("205/55 R16 zimní", price=3500)


def test_is_likely_vehicle_listing_mirrors_reject():
    assert is_likely_vehicle_listing("Díly na Golf 4", None, 2000) is False
    assert is_likely_vehicle_listing("Škoda Superb 2.0 TDI 140 kW", None, 320_000) is True


def test_reject_alu_kola_without_prodam_prefix():
    assert _reject_reason("ALU kola Škoda Octavia 16\"", price=8_000)
    assert _reject_reason("Litá kola 18 Golf 7", price=12_000)
    assert _reject_reason("Zimní kola BMW 17", price=9_500)


def test_reject_tires_without_prodam_prefix():
    assert _reject_reason("Zimní pneu Octavia 205/55", price=4_000)
    assert _reject_reason("Letní pneumatiky 16 Fabia", price=2_500)
    assert _reject_reason("Ráfky 17 VW Passat", price=3_000)
    assert _reject_reason("Felny 16 Škoda", price=1_800)


def test_reject_vin_plate_and_accessories():
    assert _reject_reason("VIN tabulka Octavia 3 originál", price=500)
    assert _reject_reason("Výrobní štítek Fabia", price=300)
    assert _reject_reason("Tažné zařízení Octavia 3", price=4_500)
    assert _reject_reason("Střešní box Thule", price=6_000)
    assert _reject_reason("Autokamera 70mai", price=1_200)
    assert _reject_reason("Koberečky Golf 7", price=800)
    assert _reject_reason("Nosič kol na tažné", price=2_000)
    assert _reject_reason("Rámeček SPZ originál Škoda", price=200)


def test_reject_glass_and_major_units_without_prodam():
    assert _reject_reason("Čelní sklo Octavia 3", price=3_500)
    assert _reject_reason("Katalyzátor Golf 4", price=2_200)
    assert _reject_reason("Alternátor 1.9 TDI", price=1_800)
    assert _reject_reason("Startér Fabia 1.2", price=900)
    assert _reject_reason("Airbag řidiče Golf 6", price=1_500)


def test_keep_car_with_alu_kola_as_equipment():
    title = "Škoda Octavia 2.0 TDI 110 kW Combi"
    popis = "Najeto 185 000 km, alu kola, serviska."
    assert _reject_reason(title, popis, 289_000) is None


def test_keep_car_with_new_tires_service_language():
    title = "VW Golf 7 1.4 TSI 92 kW"
    popis = "Nové zimní pneu 2024, STK do 2027."
    assert _reject_reason(title, popis, 245_000) is None


def test_keep_car_with_tazne_as_equipment():
    assert _reject_reason("Tesla Model Y Long Range AWD 93% Záruka Tažné", price=890_000) is None
    assert _reject_reason("BMW X2 sDrive 1.8i Automat Tažné", price=450_000) is None
    assert _reject_reason("Kia Sportage III 2.0 CRDI Ser.historie Tažné NAVI", price=189_000) is None


def test_keep_cheap_car_with_lz_pneu_equipment():
    """Winter/summer tires on a cheap whole car must not look like a tire ad."""
    assert _reject_reason("Alfa Romeo 147, 1.6i, 77kw L+Z pneu", price=18_000) is None


def test_keep_car_alu_kola_as_equipment_without_year():
    assert _reject_reason(
        "OPEL MERIVA 1.4 i BENZÍN ALU KOLA KLIMA, VYHŘEV SEDADEL",
        price=89_000,
    ) is None


def test_reject_alu_kola_when_price_is_parts_range():
    assert _reject_reason(
        'Originální Volvo V90 18" alu kola + Nokian Hakkapeliitta 9',
        price=8_000,
    )


def test_keep_car_turbo_as_engine_name():
    assert _reject_reason("Fiat Panda 0.9 TwinAir Turbo 4x4, 62,5 kW", price=139_484) is None
    assert _reject_reason("Opel Cascada 1.4 turbo", price=205_000) is None
    assert _reject_reason("Rs6 V8 Bi-turbo 550ps", price=1_190_000) is None


def test_keep_car_motor_displacement_phrase():
    assert _reject_reason("HYUNDAI i30 rok 2016, motor 1,6 DIESEL", price=99_000) is None


# --- Adapter integration: parts detail must not become ListingDTO ---


PARTS_DETAIL_HTML = """
<html><body>
  <h1 class="nadpisdetail">Náhradní díly Škoda Octavia 1.9 TDI</h1>
  <div class="popisdetail">Rozborka, motor, převodovka, kapota</div>
  <table>
    <tr><td>Lokalita:</td><td>100 00 Praha</td></tr>
    <tr><td>Cena:</td><td>5 000 Kč</td></tr>
  </table>
</body></html>
"""

CAR_DETAIL_HTML = """
<html><body>
  <h1 class="nadpisdetail">Škoda Octavia 3 Combi 1.4 TSI 110 kW</h1>
  <div class="popisdetail">
    09/2016 | 134 288 km | Benzín | STK 05/2028 | manuální převodovka.
    Po 180 tkm vyměněny rozvody.
  </div>
  <table>
    <tr><td>Lokalita:</td><td>719 00 Ostrava</td></tr>
    <tr><td>Cena:</td><td>289 000 Kč</td></tr>
  </table>
</body></html>
"""


class _FakeClient:
    def __init__(self, html: str) -> None:
        self._html = html

    def get_text(self, url: str, referer: str | None = None) -> str:
        return self._html


class _FakeConfig:
    database_url = "postgresql://invalid/no-db"
    bazos_page_size = 20


class _FakeCursors:
    def get(self, key: str) -> dict:
        return {}

    def set(self, key: str, value: dict) -> None:
        return None


def test_adapter_skips_parts_listing(monkeypatch):
    adapter = BazosAdapter(_FakeClient(PARTS_DETAIL_HTML), _FakeConfig(), _FakeCursors())
    # Avoid DB soft-hide noise in unit test
    monkeypatch.setattr(adapter, "_soft_hide_parts_listing", lambda _id: None)
    dto = adapter._fetch_detail("https://auto.bazos.cz/inzerat/123456789/dily/", brand="skoda")
    assert dto is None


def test_adapter_keeps_real_car_with_rozvody(monkeypatch):
    adapter = BazosAdapter(_FakeClient(CAR_DETAIL_HTML), _FakeConfig(), _FakeCursors())
    monkeypatch.setattr(adapter, "_soft_hide_parts_listing", lambda _id: None)
    dto = adapter._fetch_detail(
        "https://auto.bazos.cz/inzerat/987654321/octavia/", brand="skoda"
    )
    assert dto is not None
    assert dto.price_czk == 289_000
    assert dto.year == 2016


LEASE_DETAIL_HTML = """
<html><body>
  <h1 class="nadpisdetail">Škoda Octavia 1.5 TSI operativní leasing</h1>
  <div class="popisdetail">Předplatné, 8 900 Kč/měsíc, na splátky formou operáku.</div>
  <table>
    <tr><td>Lokalita:</td><td>100 00 Praha</td></tr>
    <tr><td>Cena:</td><td>8 900 Kč</td></tr>
  </table>
</body></html>
"""


def test_adapter_skips_leasing_listing(monkeypatch):
    adapter = BazosAdapter(_FakeClient(LEASE_DETAIL_HTML), _FakeConfig(), _FakeCursors())
    monkeypatch.setattr(adapter, "_soft_hide_parts_listing", lambda _id: None)
    dto = adapter._fetch_detail(
        "https://auto.bazos.cz/inzerat/111222333/operak/", brand="skoda"
    )
    assert dto is None


def test_table_value_still_works_after_filter_import():
    soup = BeautifulSoup(CAR_DETAIL_HTML, "lxml")
    assert BazosAdapter._table_value(soup, "Cena") == "289 000 Kč"
