import random
from datetime import datetime, timezone
from decimal import Decimal

from plungepalz_calories import (
    DEFAULT_CALORIES,
    estimate_calories,
    fetch_user_profile_fields,
)
from plungepalz_calories.constants import MIN_CALORIES, MODEL_VERSION, NON_PREMIUM_CALORIES
from plungepalz_calories.model import _resolve_premium

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)

DOCUMENTED_KEYS = {
    "calories",
    "total_kcal",
    "net_kcal",
    "multiplier",
    "rmr_kcal_min",
    "minutes",
    "temp_f_used",
    "activity_type",
    "model_version",
    "confidence",
    "is_premium",
    "premium_gated",
    "fallback_used",
    "flags",
}

PROFILE = dict(
    user_height="5'10\"",
    user_weight="180 lb",
    gender="Male",
    date_of_birth="1986-09-10",
    is_premium=True,
    as_of=AS_OF,
)


def test_not_premium_gate_is_first():
    result = estimate_calories("Cold Plunge", 50.0, 180.0, **{**PROFILE, "is_premium": False})
    assert result["calories"] == NON_PREMIUM_CALORIES
    assert result["fallback_used"] is False
    assert result["premium_gated"] is True
    assert "not_premium" in result["flags"]


def test_exception_before_premium_resolves(monkeypatch):
    def boom(_value):
        raise RuntimeError("resolver failed")

    monkeypatch.setattr("plungepalz_calories.model._resolve_premium", boom)
    result = estimate_calories("Cold Plunge", 50.0, 180.0, **PROFILE)
    assert result["calories"] == NON_PREMIUM_CALORIES
    assert result["fallback_used"] is True
    assert "exception" in result["flags"]


def test_invalid_duration_fallback():
    for duration in (None, "", "abc", 0, -5, "0"):
        result = estimate_calories("Cold Plunge", 50.0, duration, **PROFILE)
        assert result["calories"] == DEFAULT_CALORIES
        assert result["fallback_used"] is True
        assert "invalid_duration" in result["flags"]


def test_unknown_activity_type_is_pure_rmr():
    result = estimate_calories("Ice Bath", 50.0, 180.0, **PROFILE)
    assert result["fallback_used"] is False
    assert "unknown_activity_type" in result["flags"]
    assert result["multiplier"] == 1.0
    assert result["confidence"] == "unknown"
    expected_total = result["rmr_kcal_min"] * result["minutes"]
    assert abs(result["total_kcal"] - expected_total) < 1e-9
    assert abs(result["net_kcal"]) < 1e-9


def test_temp_defaulted():
    result = estimate_calories("Cold Plunge", None, 180.0, **PROFILE)
    assert result["fallback_used"] is False
    assert "temp_defaulted" in result["flags"]
    assert result["temp_f_used"] == 50.0

    result = estimate_calories("Cold Plunge", 200.0, 180.0, **PROFILE)
    assert "temp_defaulted" in result["flags"]
    assert result["temp_f_used"] == 50.0


def test_blank_profile_flags():
    result = estimate_calories(
        "Cold Plunge",
        50.0,
        180.0,
        user_height="",
        user_weight=None,
        gender="",
        date_of_birth="",
        is_premium=True,
        as_of=AS_OF,
    )
    assert result["fallback_used"] is False
    assert "default_height" in result["flags"]
    assert "default_weight" in result["flags"]
    assert "default_age" in result["flags"]
    assert "default_sex" in result["flags"]


def test_min_floor_applied():
    result = estimate_calories("Sauna", 180.0, 1.0, **PROFILE)
    assert result["calories"] == MIN_CALORIES
    assert result["fallback_used"] is False
    assert "min_floor_applied" in result["flags"]


def test_duration_coercion_agreement():
    results = [
        estimate_calories("Sauna", 180.0, duration, **PROFILE)
        for duration in ("97", 97, 97.0, Decimal("97"))
    ]
    calories = {r["calories"] for r in results}
    totals = {round(r["total_kcal"], 8) for r in results}
    assert len(calories) == 1
    assert len(totals) == 1


def test_temp_coercion_agreement():
    results = [
        estimate_calories("Cold Plunge", temp, 78.0, **PROFILE)
        for temp in ("45.0", 45, Decimal("45.0"))
    ]
    calories = {r["calories"] for r in results}
    multipliers = {round(r["multiplier"], 8) for r in results}
    assert len(calories) == 1
    assert len(multipliers) == 1


def test_exception_does_not_propagate(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(
        "plungepalz_calories.model.build_user_profile",
        boom,
    )
    result = estimate_calories("Cold Plunge", 45.0, 78.0, **PROFILE)
    assert result["calories"] == DEFAULT_CALORIES
    assert result["fallback_used"] is True
    assert "exception" in result["flags"]
    assert result["model_version"] == MODEL_VERSION


def test_fetch_user_profile_fields_without_boto3():
    assert fetch_user_profile_fields("any-account") == {}


def test_fuzz_never_raises():
    rng = random.Random(20260910)
    activities = [
        "Cold Plunge",
        "Sauna",
        "Cold Shower",
        "Hot Tub",
        "Steam Room",
        "ice bath",
        "not-a-type",
        "",
        "  sauna  ",
    ]
    temps = list(range(-100, 501, 17)) + [None, "", "abc"]
    durations = list(range(-100, 100001, 1373)) + [None, "", "abc", "12.5"]
    heights = [None, "", "5'11\"", "abc", "180", "1'2\""]
    weights = [None, "", "160.0 lbs", "0 lbs", "999 kgs", "72"]
    genders = [None, "", "Male", "Female", "Other"]
    dobs = [None, "", "1971-06-04", "not-a-date", "3000-01-01"]
    uoms = [None, "Imperial", "Metric", ""]
    premiums = [True, False, None, "", "true", "false", 0, 1, "no", "premium"]

    for i in range(2000):
        is_premium = rng.choice(premiums)
        result = estimate_calories(
            rng.choice(activities),
            rng.choice(temps),
            rng.choice(durations),
            user_height=rng.choice(heights),
            user_weight=rng.choice(weights),
            gender=rng.choice(genders),
            date_of_birth=rng.choice(dobs),
            unit_of_measure=rng.choice(uoms),
            is_premium=is_premium,
            as_of=AS_OF,
        )
        assert isinstance(result["calories"], int), i
        assert DOCUMENTED_KEYS <= set(result.keys()), i
        if _resolve_premium(is_premium) is True:
            assert 1 <= result["calories"] <= 5000, (i, result["calories"])
        else:
            assert result["calories"] == 0, (i, is_premium, result["calories"])
