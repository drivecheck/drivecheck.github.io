from bs4 import BeautifulSoup

from drivecheck_crawler.adapters.bazos import _extract_cover_image_url
from drivecheck_crawler.thumbs.urls import (
    guess_bazos_cover_url,
    prepare_download_url,
    resolve_cover_url,
)


def test_extract_cover_skips_logo_svg():
    html = """
    <html><body>
      <img src="https://www.bazos.cz/obrazky/bazos.svg" />
      <img class="carousel-cell-image"
           data-flickity-lazyload="https://www.bazos.cz/img/1/059/221941059.jpg"
           src="https://www.bazos.cz/img/1/059/221941059.jpg" />
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert (
        _extract_cover_image_url(soup, "221941059")
        == "https://www.bazos.cz/img/1/059/221941059.jpg"
    )


def test_guess_bazos_cover_from_id():
    assert guess_bazos_cover_url("221941059") == "https://www.bazos.cz/img/1/059/221941059.jpg"


def test_resolve_cover_replaces_svg():
    assert (
        resolve_cover_url(
            source="bazos",
            external_id="221941059",
            image_url="https://www.bazos.cz/obrazky/bazos.svg",
        )
        == "https://www.bazos.cz/img/1/059/221941059.jpg"
    )


def test_prepare_download_url_adds_sauto_cdn_transform():
    src = "https://d19-a.sdn.cz/d_19/c_img_qE_A/example/61ab.jpeg"
    out = prepare_download_url(src)
    assert out.startswith(src + "?fl=")
    assert "wrm,/watermark/sauto.png" in out
    assert prepare_download_url(out) == out  # idempotent
