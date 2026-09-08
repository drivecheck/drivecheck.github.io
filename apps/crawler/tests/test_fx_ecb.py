from datetime import date

from drivecheck_crawler.fx import clear_live_rates, set_live_rates, to_czk
from drivecheck_crawler.fx_ecb import parse_ecb_daily_xml

ECB_FIXTURE = """<?xml version="1.0"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
  xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-08-14">
      <Cube currency="USD" rate="1.10"/>
      <Cube currency="CZK" rate="24.50"/>
      <Cube currency="PLN" rate="4.25"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


def test_parse_ecb_daily_xml():
    quoted_on, rates = parse_ecb_daily_xml(ECB_FIXTURE)
    assert quoted_on == date(2026, 8, 14)
    assert rates["EUR"] == 24.5
    assert rates["CZK"] == 1.0
    # 1 PLN = 24.50 / 4.25 CZK
    assert abs(rates["PLN"] - (24.5 / 4.25)) < 1e-9
    assert abs(rates["USD"] - (24.5 / 1.10)) < 1e-9


def test_to_czk_uses_live_ecb_rates():
    quoted_on, rates = parse_ecb_daily_xml(ECB_FIXTURE)
    set_live_rates(rates, quoted_on)
    try:
        # 1000 EUR * 24.50 = 24500
        assert to_czk(1000, "EUR") == 24_500
    finally:
        clear_live_rates()
