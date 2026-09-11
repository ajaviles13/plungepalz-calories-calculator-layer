from datetime import datetime, timezone

from plungepalz_calories.constants import (
    DEFAULT_AGE_YEARS,
    DEFAULT_SEX,
    LB_TO_KG,
)
from plungepalz_calories.profile import (
    age_from_dob,
    build_user_profile,
    parse_height_cm,
    parse_sex,
    parse_weight_kg,
)

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)
DEFAULT_HEIGHT_CM = (5 * 12 + 11) * 2.54  # 180.34
DEFAULT_WEIGHT_KG = 160.0 * LB_TO_KG      # 72.57472


def test_parse_height_table():
    cases = [
        ("5'11\"", 180.34),
        ("5'11", 180.34),
        ("6'0\"", 182.88),
        ("5'", 152.4),
        ("169.2 cms", 169.2),
        ("173 cm", 173.0),
    ]
    for raw, expected in cases:
        cm, flag = parse_height_cm(raw)
        assert flag is None, raw
        assert cm == expected, raw


def test_parse_height_bare_metric():
    cm, flag = parse_height_cm("180", unit_of_measure="Metric")
    assert flag is None
    assert cm == 180.0


def test_parse_height_defaults():
    for raw in ("", None, "N/A", "5 foot"):
        cm, flag = parse_height_cm(raw)
        assert flag == "default_height", raw
        assert cm == DEFAULT_HEIGHT_CM, raw


def test_parse_height_garbage_and_bounds():
    cm, flag = parse_height_cm("abc")
    assert flag == "default_height"
    assert cm == DEFAULT_HEIGHT_CM

    cm, flag = parse_height_cm("1'2\"")
    assert flag == "height_out_of_bounds"
    assert cm == DEFAULT_HEIGHT_CM


def test_parse_height_bare_number_uom():
    cm, flag = parse_height_cm("70", unit_of_measure="Imperial")
    assert flag is None
    assert cm == 70 * 2.54

    cm, flag = parse_height_cm("180", unit_of_measure="Metric")
    assert flag is None
    assert cm == 180.0

    cm, flag = parse_height_cm("180", unit_of_measure=None)
    assert flag == "default_height"
    assert cm == DEFAULT_HEIGHT_CM


def test_parse_weight_table():
    cases = [
        ("150.0 lbs", 150.0 * LB_TO_KG),
        ("203 lb", 203 * LB_TO_KG),
        ("100.0 kgs", 100.0),
        ("72 kg", 72.0),
    ]
    for raw, expected in cases:
        kg, flag = parse_weight_kg(raw)
        assert flag is None, raw
        assert kg == expected, raw


def test_parse_weight_bare_imperial():
    kg, flag = parse_weight_kg("160", unit_of_measure="Imperial")
    assert flag is None
    assert kg == 160.0 * LB_TO_KG


def test_parse_weight_defaults_and_garbage():
    for raw in ("", None, "N/A", "abc"):
        kg, flag = parse_weight_kg(raw)
        assert flag == "default_weight", raw
        assert kg == DEFAULT_WEIGHT_KG, raw

    kg, flag = parse_weight_kg("0 lbs")
    assert flag == "weight_out_of_bounds"
    assert kg == DEFAULT_WEIGHT_KG

    kg, flag = parse_weight_kg("999 kgs")
    assert flag == "weight_out_of_bounds"
    assert kg == DEFAULT_WEIGHT_KG


def test_parse_weight_bare_number_uom():
    kg, flag = parse_weight_kg("160", unit_of_measure="Imperial")
    assert flag is None
    assert kg == 160.0 * LB_TO_KG

    kg, flag = parse_weight_kg("72", unit_of_measure="Metric")
    assert flag is None
    assert kg == 72.0

    kg, flag = parse_weight_kg("160", unit_of_measure=None)
    assert flag == "default_weight"
    assert kg == DEFAULT_WEIGHT_KG


def test_age_from_dob_fixed_as_of():
    age, flag = age_from_dob("1971-06-04", as_of=AS_OF)
    assert flag is None
    assert age == 55


def test_age_birthday_today_and_tomorrow():
    age, flag = age_from_dob("1971-09-10", as_of=AS_OF)
    assert flag is None
    assert age == 55

    age, flag = age_from_dob("1971-09-11", as_of=AS_OF)
    assert flag is None
    assert age == 54


def test_age_leap_day_future_and_blank():
    age, flag = age_from_dob("2000-02-29", as_of=AS_OF)
    assert flag is None
    assert age == 26

    age, flag = age_from_dob("3000-01-01", as_of=AS_OF)
    assert flag == "default_age"
    assert age == DEFAULT_AGE_YEARS

    age, flag = age_from_dob("", as_of=AS_OF)
    assert flag == "default_age"
    assert age == DEFAULT_AGE_YEARS


def test_gender_mapping():
    assert parse_sex("male") == ("male", None)
    assert parse_sex("FEMALE") == ("female", None)
    assert parse_sex("") == (DEFAULT_SEX, "default_sex")
    assert parse_sex(None) == (DEFAULT_SEX, "default_sex")
    assert parse_sex("Other") == (DEFAULT_SEX, "default_sex")


def test_rmr_male_reference():
    profile = build_user_profile(
        user_height="5'10\"",
        user_weight="180 lb",
        gender="Male",
        date_of_birth="1986-09-10",
        as_of=AS_OF,
    )
    assert profile["age_years"] == 40
    assert profile["sex"] == "male"
    assert abs(profile["rmr_kcal_day"] - 1732.75) < 0.5
    assert abs(profile["rmr_kcal_min"] - 1.2033) < 0.001


def test_rmr_female_reference():
    profile = build_user_profile(
        user_height="5'5\"",
        user_weight="140 lb",
        gender="Female",
        date_of_birth="1986-09-10",
        as_of=AS_OF,
    )
    assert profile["age_years"] == 40
    assert profile["sex"] == "female"
    assert abs(profile["rmr_kcal_day"] - 1305.90) < 0.5
    assert abs(profile["rmr_kcal_min"] - 0.9069) < 0.001
