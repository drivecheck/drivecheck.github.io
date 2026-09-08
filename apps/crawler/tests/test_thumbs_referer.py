from drivecheck_crawler.thumbs.urls import download_referer_for_source


def test_download_referer_per_source():
    assert download_referer_for_source("tipcars") == "https://www.tipcars.com/"
    assert (
        download_referer_for_source("autobazar_eu")
        == "https://www.autobazar.eu/cs/"
    )
    assert download_referer_for_source("mobile_de") == "https://suchen.mobile.de/"
    assert (
        download_referer_for_source("autoscout24") == "https://www.autoscout24.de/"
    )
    assert download_referer_for_source("sauto") == "https://www.sauto.cz/"


def test_bazos_prefers_listing_url():
    listing = "https://auto.bazos.cz/inzerat/1/skoda.php"
    assert download_referer_for_source("bazos", listing_url=listing) == listing
    assert download_referer_for_source("bazos") == "https://auto.bazos.cz/"


def test_tipcars_does_not_use_sauto_referer():
    assert download_referer_for_source("tipcars") != "https://www.sauto.cz/"
    assert download_referer_for_source("autobazar_eu") != "https://www.sauto.cz/"
