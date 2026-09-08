from drivecheck_crawler.probe import (
    ProbeVerdict,
    classify_http_status,
    probe_autobazar_eu_listing,
    probe_bazos_listing,
    probe_sauto_item,
    probe_tipcars_listing,
    sauto_item_body_verdict,
)


class FakeClient:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, str]] = []

    def request_raw(self, method, url, *, params=None, headers=None):
        self.calls.append((method, url))
        return self.status, self.body


def test_classify_http_status():
    assert classify_http_status(200) is ProbeVerdict.LIVE
    assert classify_http_status(404) is ProbeVerdict.GONE
    assert classify_http_status(410) is ProbeVerdict.GONE
    assert classify_http_status(429) is ProbeVerdict.UNCERTAIN
    assert classify_http_status(503) is ProbeVerdict.UNCERTAIN
    assert classify_http_status(403) is ProbeVerdict.UNCERTAIN


def test_probe_sauto_gone_and_live():
    assert (
        probe_sauto_item(FakeClient(404, b'{"error":"Not found"}'), "1")
        is ProbeVerdict.GONE
    )
    assert probe_sauto_item(FakeClient(200, b'{"result":{}}'), "1") is ProbeVerdict.LIVE
    assert probe_sauto_item(FakeClient(429, b""), "1") is ProbeVerdict.UNCERTAIN
    # Soft-deleted: HTTP 200 + status=deleted (real Sauto behavior).
    assert (
        probe_sauto_item(
            FakeClient(200, b'{"result":{"id":1,"status":"deleted","name":"X"}}'),
            "1",
        )
        is ProbeVerdict.GONE
    )
    assert (
        probe_sauto_item(
            FakeClient(200, b'{"result":{"id":1,"status":"active","name":"X"}}'),
            "1",
        )
        is ProbeVerdict.LIVE
    )


def test_sauto_item_body_verdict():
    assert sauto_item_body_verdict(b'{"result":{"status":"deleted"}}') is ProbeVerdict.GONE
    assert sauto_item_body_verdict(b'{"status":"inactive"}') is ProbeVerdict.GONE
    assert sauto_item_body_verdict(b'{"result":{"status":"active"}}') is ProbeVerdict.LIVE
    assert sauto_item_body_verdict(b'{"result":{}}') is None
    assert sauto_item_body_verdict(b"not-json") is None


def test_probe_bazos_soft_dead_title():
    html = (
        b"<html><head><title>Inzerat neexistuje - Bazos.cz</title></head>"
        b"<body>Inzerat byl odstranen</body></html>"
    )
    assert (
        probe_bazos_listing(
            FakeClient(200, html),
            url="https://auto.bazos.cz/inzerat/1/x.php",
            external_id="1",
        )
        is ProbeVerdict.GONE
    )


def test_probe_bazos_410():
    assert (
        probe_bazos_listing(
            FakeClient(410, b""),
            url="https://auto.bazos.cz/inzerat/1/x.php",
            external_id="1",
        )
        is ProbeVerdict.GONE
    )


def test_probe_tipcars_404_and_live():
    url = "https://www.tipcars.com/skoda/octavia/x-12345678.html"
    assert (
        probe_tipcars_listing(FakeClient(404, b""), url=url, external_id="12345678")
        is ProbeVerdict.GONE
    )
    assert (
        probe_tipcars_listing(
            FakeClient(
                200,
                b"<html><title>Skoda Octavia - TipCars</title><body>ok</body></html>",
            ),
            url=url,
            external_id="12345678",
        )
        is ProbeVerdict.LIVE
    )
    assert (
        probe_tipcars_listing(FakeClient(429, b""), url=url, external_id="12345678")
        is ProbeVerdict.UNCERTAIN
    )


def test_probe_tipcars_soft_dead_title():
    html = (
        b"<html><head><title>Stranka neexistuje - TipCars</title></head>"
        b"<body>Inzerat nenalezen</body></html>"
    )
    assert (
        probe_tipcars_listing(
            FakeClient(200, html),
            url="https://www.tipcars.com/x-1.html",
            external_id="1",
        )
        is ProbeVerdict.GONE
    )


def test_probe_autobazar_eu_404_and_live():
    url = "https://www.autobazar.eu/cs/detail/skoda-octavia/AmTestCzOct1/"
    assert (
        probe_autobazar_eu_listing(
            FakeClient(404, b""), url=url, external_id="AmTestCzOct1"
        )
        is ProbeVerdict.GONE
    )
    assert (
        probe_autobazar_eu_listing(
            FakeClient(
                200,
                b"<html><title>Skoda Octavia - Autobazar.EU</title><body>ok</body></html>",
            ),
            url=url,
            external_id="AmTestCzOct1",
        )
        is ProbeVerdict.LIVE
    )
    assert (
        probe_autobazar_eu_listing(
            FakeClient(429, b""), url=url, external_id="AmTestCzOct1"
        )
        is ProbeVerdict.UNCERTAIN
    )
    assert (
        probe_autobazar_eu_listing(
            FakeClient(503, b""), url=url, external_id="AmTestCzOct1"
        )
        is ProbeVerdict.UNCERTAIN
    )


def test_probe_autobazar_eu_soft_dead_title():
    html = (
        b"<html><head><title>404 - stranka nebyla nalezena | Autobazar.EU</title></head>"
        b"<body>Inzerat neexistuje</body></html>"
    )
    assert (
        probe_autobazar_eu_listing(
            FakeClient(200, html),
            url="https://www.autobazar.eu/cs/detail/x/AmGone/",
            external_id="AmGone",
        )
        is ProbeVerdict.GONE
    )
