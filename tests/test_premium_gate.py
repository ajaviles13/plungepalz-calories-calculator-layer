from datetime import datetime, timezone

from plungepalz_calories import DEFAULT_CALORIES, estimate_calories
from plungepalz_calories.constants import NON_PREMIUM_CALORIES

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)

PREMIUM_INPUTS = dict(
    user_height="5'10\"",
    user_weight="180 lb",
    gender="Male",
    date_of_birth="1986-09-10",
    as_of=AS_OF,
)


def _computed_keys():
    return set(
        estimate_calories(
            "Cold Plunge",
            50.0,
            180.0,
            is_premium=True,
            **PREMIUM_INPUTS,
        ).keys()
    )


def test_true_and_string_true_compute():
    for value in (True, "true"):
        result = estimate_calories(
            "Cold Plunge",
            50.0,
            180.0,
            is_premium=value,
            **PREMIUM_INPUTS,
        )
        assert result["premium_gated"] is False
        assert result["is_premium"] is True
        assert result["calories"] > 0
        assert result["fallback_used"] is False


def test_non_premium_values_are_gated():
    expected_keys = _computed_keys()
    cases = [False, None, "", "false", "False", 0, "no", "premium", [], {}]
    for value in cases:
        result = estimate_calories(
            "Cold Plunge",
            50.0,
            180.0,
            is_premium=value,
            **PREMIUM_INPUTS,
        )
        assert result["calories"] == 0, value
        assert result["premium_gated"] is True, value
        assert result["confidence"] == "gated", value
        assert result["flags"] == ["not_premium"], value
        assert result["total_kcal"] == 0.0, value
        assert result["net_kcal"] == 0.0, value
        assert result["multiplier"] == 0.0, value
        assert sorted(result.keys()) == sorted(expected_keys), value


def test_omitted_is_premium_is_gated():
    expected_keys = _computed_keys()
    result = estimate_calories("Cold Plunge", 50.0, 180.0, **PREMIUM_INPUTS)
    assert result["calories"] == 0
    assert result["premium_gated"] is True
    assert result["confidence"] == "gated"
    assert result["flags"] == ["not_premium"]
    assert result["total_kcal"] == 0.0
    assert result["net_kcal"] == 0.0
    assert sorted(result.keys()) == sorted(expected_keys)


def test_gate_short_circuits_perfect_inputs():
    result = estimate_calories(
        "Cold Plunge",
        45.0,
        78.0,
        is_premium=False,
        **PREMIUM_INPUTS,
    )
    assert result["calories"] == 0
    assert result["multiplier"] == 0.0
    assert result["minutes"] == 0.0
    assert result["rmr_kcal_min"] == 0.0
    assert result["premium_gated"] is True


def test_min_calories_does_not_lift_gated_zero():
    result = estimate_calories(
        "Cold Plunge",
        50.0,
        10 * 60,
        is_premium=False,
        **PREMIUM_INPUTS,
    )
    assert result["calories"] == 0
    assert result["premium_gated"] is True

    premium = estimate_calories(
        "Cold Plunge",
        50.0,
        10 * 60,
        is_premium=True,
        **PREMIUM_INPUTS,
    )
    assert premium["calories"] >= 30


def test_profile_exception_is_fail_closed(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr("plungepalz_calories.model.build_user_profile", boom)

    premium = estimate_calories(
        "Cold Plunge",
        45.0,
        78.0,
        is_premium=True,
        **PREMIUM_INPUTS,
    )
    assert premium["calories"] == DEFAULT_CALORIES
    assert premium["fallback_used"] is True
    assert "exception" in premium["flags"]

    for value in (False, None):
        gated = estimate_calories(
            "Cold Plunge",
            45.0,
            78.0,
            is_premium=value,
            **PREMIUM_INPUTS,
        )
        assert gated["calories"] == NON_PREMIUM_CALORIES, value
        assert gated["calories"] != DEFAULT_CALORIES, value


def test_resolve_premium_raise_returns_zero_not_fifteen(monkeypatch):
    def boom(_value):
        raise RuntimeError("resolver failed")

    monkeypatch.setattr("plungepalz_calories.model._resolve_premium", boom)
    result = estimate_calories(
        "Cold Plunge",
        45.0,
        78.0,
        is_premium=True,
        **PREMIUM_INPUTS,
    )
    assert result["calories"] == 0
    assert result["calories"] != DEFAULT_CALORIES
