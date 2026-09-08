from drivecheck_crawler.accident import (
    ACCIDENT_FEATURE_KEY,
    is_accident_or_damaged_listing,
    should_skip_accident_listing,
    text_suggests_accident_or_damage,
)


def test_cz_havarovane_title():
    assert text_suggests_accident_or_damage("Škoda Octavia havarovaná levně")
    assert should_skip_accident_listing(title="Po nehodě, pojízdná")


def test_cz_nahradni_dily():
    assert should_skip_accident_listing(title="Golf na náhradní díly")


def test_de_unfallwagen():
    assert should_skip_accident_listing(title="VW Golf Unfallwagen")
    assert should_skip_accident_listing(title="Bastlerfahrzeug Motorschaden")
    assert should_skip_accident_listing(
        flags={"isCurrentlyDamaged": True},
        title="Opel Corsa",
    )
    assert should_skip_accident_listing(
        special_conditions=["AccidentDamaged"],
        title="BMW 320d",
    )


def test_feature_key_tag():
    assert is_accident_or_damaged_listing(
        feature_keys=[ACCIDENT_FEATURE_KEY, "heated_seats"]
    )


def test_does_not_overfilter_service_language():
    assert not text_suggests_accident_or_damage("Serviska, nové brzdy, pneu 2024")
    assert not should_skip_accident_listing(
        title="Octavia RS servisní knížka, nové brzdy"
    )
    assert not should_skip_accident_listing(
        title="Seat Leon FR",
        feature_keys=["heated_seats", "parking_camera"],
        flags={"isCurrentlyDamaged": False},
    )
