from drivecheck_crawler.features import normalize_feature_list, normalize_feature_name
from drivecheck_crawler.normalize import extract_features_from_text, strip_contact_text


def test_feature_aliases():
    assert normalize_feature_name("Panoramatická střecha") == "panorama"
    assert normalize_feature_name("Apple Car Play") == "apple_carplay"
    assert "panorama" in normalize_feature_list(["Panorama", "ABS"])
    assert normalize_feature_name("Adaptivní tempomat") == "cruise_control"
    assert normalize_feature_name("Mrtvý úhel") == "blind_spot"
    assert normalize_feature_name("Elektrické otevírání kufru") == "electric_tailgate"
    assert normalize_feature_name("Masážní sedadla") == "massage_seats"
    assert normalize_feature_name("Jízda v pruhu") == "lane_assist"
    assert normalize_feature_name("Nezávislé topení") == "aux_heater"
    assert normalize_feature_name("Tovární záruka") == "factory_warranty"
    assert normalize_feature_name("Vzduchový podvozek") == "air_suspension"


def test_strip_contact_text():
    text = strip_contact_text("Volejte +420 603 589 309 nebo mail test@example.com")
    assert "603" not in text
    assert "example.com" not in text
    assert "[redacted]" in text


def test_extract_features_from_title():
    keys = extract_features_from_text("Škoda Enyaq Sportline Panorama Kamera 4x4")
    assert "sportline" in keys
    assert "panorama" in keys


def test_extract_equipment_catalog_from_text():
    keys = extract_features_from_text(
        "Keyless tempomat mrtvý úhel masáž webasto tovární záruka vzduchový podvozek"
    )
    assert "keyless" in keys
    assert "cruise_control" in keys
    assert "blind_spot" in keys
    assert "massage_seats" in keys
    assert "aux_heater" in keys
    assert "factory_warranty" in keys
    assert "air_suspension" in keys
