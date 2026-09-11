from datetime import datetime, timezone

from plungepalz_calories import estimate_calories
from plungepalz_calories.profile import build_user_profile

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)

PROFILE = dict(
    user_height="5'8\"",
    user_weight="150.0 lbs",
    gender="",
    date_of_birth="1971-06-04",
    is_premium=True,
    as_of=AS_OF,
)
PROFILE_FIELDS = dict(
    user_height="5'8\"",
    user_weight="150.0 lbs",
    gender="",
    date_of_birth="1971-06-04",
    as_of=AS_OF,
)


def test_production_profile_rmr():
    profile = build_user_profile(**PROFILE_FIELDS)
    assert profile["sex"] == "male"
    assert profile["age_years"] == 55
    assert "default_sex" in profile["flags"]
    assert abs(profile["rmr_kcal_min"] - 1.0346) < 0.001


def test_garmin_sample_1_cold_plunge():
    result = estimate_calories("Cold Plunge", "45.0", "78", **PROFILE)
    assert result["calories"] == 7
    assert result["fallback_used"] is False


def test_garmin_sample_2_sauna():
    result = estimate_calories("Sauna", "180.0", "76", **PROFILE)
    assert result["calories"] == 1
    assert result["fallback_used"] is False


def test_mobile_sample_3_sauna():
    result = estimate_calories("Sauna", "180.0", "97", **PROFILE)
    assert result["calories"] == 2
    assert result["fallback_used"] is False


def test_twenty_minute_sauna_regression_guard():
    result = estimate_calories("Sauna", "180.0", "1200", **PROFILE)
    assert result["calories"] == 23
    assert abs(result["total_kcal"] - 23.06) < 0.2
    assert result["net_kcal"] < 2.5
    assert abs(result["net_kcal"] - 2.37) < 0.2


def test_garmin_sample_1_not_premium():
    result = estimate_calories("Cold Plunge", "45.0", "78", **{**PROFILE_FIELDS, "is_premium": False})
    assert result["calories"] == 0
    assert result["premium_gated"] is True
    assert result["confidence"] == "gated"
    assert result["flags"] == ["not_premium"]


def test_mobile_sample_3_premium_omitted():
    result = estimate_calories("Sauna", "180.0", "97", **PROFILE_FIELDS)
    assert result["calories"] == 0
    assert result["premium_gated"] is True
    assert "not_premium" in result["flags"]
