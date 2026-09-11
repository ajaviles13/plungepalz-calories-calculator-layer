"""Calorie-burn model for contrast-therapy activities.

Never raises to the caller. Any failure returns DEFAULT_CALORIES with
fallback_used=True.
"""

from __future__ import annotations

import logging
import math

from .constants import (
    ACTIVITY_TEMP_DEFAULTS,
    ACTIVITY_TEMP_RANGES,
    COLD_MAX_MULTIPLIER,
    COLD_MILD_SLOPE,
    COLD_STEEP_BASE_M,
    COLD_STEEP_BREAK_C,
    COLD_STEEP_SLOPE,
    COLD_THERMONEUTRAL_C,
    COLD_WATER_FLOOR_C,
    CONFIDENCE,
    DEFAULT_CALORIES,
    HEAT_MAX_MULTIPLIER,
    HOT_MAX_MULTIPLIER,
    HOT_SLOPE,
    HOT_THERMONEUTRAL_C,
    MAX_DURATION_SECONDS,
    MIN_CALORIES,
    MODEL_VERSION,
    Q10_DTC_BASELINE_C,
    Q10_DTC_COEFFICIENT,
    Q10_DTC_MAX,
    Q10_PER_DEGREE,
    SHOWER_ATTENUATION,
    STEAM_HUMIDITY_OFFSET_C,
)
from .profile import build_user_profile

logger = logging.getLogger(__name__)

_RESULT_KEYS = (
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
    "fallback_used",
    "flags",
)

_COLD_FAMILY = frozenset({"Cold Plunge", "Cold Shower"})
_HOT_WATER_FAMILY = frozenset({"Hot Tub"})
_Q10_FAMILY = frozenset({"Sauna", "Steam Room"})
_UNKNOWN_DURATION_CEILING = max(MAX_DURATION_SECONDS.values())


def cold_multiplier(t_c: float) -> float:
    """Cold-immersion MET multiplier (Šrámek 2000 / Eyolfson 2001)."""
    t = max(t_c, COLD_WATER_FLOOR_C)
    if t >= COLD_THERMONEUTRAL_C:
        m = 1.0
    elif t >= COLD_STEEP_BREAK_C:
        m = 1.0 + (COLD_THERMONEUTRAL_C - t) * COLD_MILD_SLOPE
    else:
        m = COLD_STEEP_BASE_M + (COLD_STEEP_BREAK_C - t) * COLD_STEEP_SLOPE
    return min(m, COLD_MAX_MULTIPLIER)


def hot_multiplier(t_c: float) -> float:
    """Hot-water MET multiplier (Faulkner 2017)."""
    m = 1.0 if t_c <= HOT_THERMONEUTRAL_C else 1.0 + (t_c - HOT_THERMONEUTRAL_C) * HOT_SLOPE
    return min(m, HOT_MAX_MULTIPLIER)


def q10_values(t_c: float, minutes: float, steam: bool = False):
    """Return ``(multiplier, dTc)`` for the Q10 heat family."""
    t_eff = t_c + (STEAM_HUMIDITY_OFFSET_C if steam else 0.0)
    dTc = Q10_DTC_COEFFICIENT * (t_eff - Q10_DTC_BASELINE_C) * minutes
    dTc = min(max(dTc, 0.0), Q10_DTC_MAX)
    m = min(1.0 + Q10_PER_DEGREE * dTc, HEAT_MAX_MULTIPLIER)
    return m, dTc


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _canonical_activity(activity_type):
    if activity_type is None:
        return None, True
    text = str(activity_type).strip()
    if not text:
        return None, True
    lowered = text.lower()
    for name in ACTIVITY_TEMP_RANGES:
        if name.lower() == lowered:
            return name, False
    return text, True


def _log_flags(flags):
    for flag in flags:
        logger.info("calorie model flag: %s", flag)


def _result(
    *,
    calories,
    total_kcal,
    net_kcal,
    multiplier,
    rmr_kcal_min,
    minutes,
    temp_f_used,
    activity_type,
    confidence,
    fallback_used,
    flags,
):
    return {
        "calories": int(calories),
        "total_kcal": float(total_kcal),
        "net_kcal": float(net_kcal),
        "multiplier": float(multiplier),
        "rmr_kcal_min": float(rmr_kcal_min),
        "minutes": float(minutes),
        "temp_f_used": None if temp_f_used is None else float(temp_f_used),
        "activity_type": activity_type,
        "model_version": MODEL_VERSION,
        "confidence": confidence,
        "fallback_used": bool(fallback_used),
        "flags": list(flags),
    }


def _fallback_result(
    *,
    flag,
    activity_type=None,
    confidence="unknown",
    minutes=0.0,
    temp_f_used=None,
    multiplier=1.0,
    rmr_kcal_min=0.0,
    extra_flags=None,
):
    flags = [flag]
    if extra_flags:
        flags.extend(extra_flags)
    logger.warning("calorie model fallback: %s", flag)
    _log_flags(flags)
    return _result(
        calories=DEFAULT_CALORIES,
        total_kcal=float(DEFAULT_CALORIES),
        net_kcal=0.0,
        multiplier=multiplier,
        rmr_kcal_min=rmr_kcal_min,
        minutes=minutes,
        temp_f_used=temp_f_used,
        activity_type=activity_type,
        confidence=confidence,
        fallback_used=True,
        flags=flags,
    )


def estimate_calories(
    activity_type,
    temp_f,
    duration_seconds,
    user_height=None,
    user_weight=None,
    gender=None,
    date_of_birth=None,
    unit_of_measure=None,
    as_of=None,
) -> dict:
    """Estimate total kcal for a contrast-therapy session. Never raises."""
    try:
        flags = []

        canonical, unknown = _canonical_activity(activity_type)
        if unknown:
            flags.append("unknown_activity_type")
            multiplier_forced = 1.0
            confidence = "unknown"
            activity_name = canonical
        else:
            multiplier_forced = None
            confidence = CONFIDENCE[canonical]
            activity_name = canonical

        duration = _to_float(duration_seconds)
        if duration is None or duration <= 0:
            return _fallback_result(
                flag="invalid_duration",
                activity_type=activity_name,
                confidence=confidence,
                extra_flags=[f for f in flags if f != "invalid_duration"],
            )

        ceiling = MAX_DURATION_SECONDS.get(activity_name, _UNKNOWN_DURATION_CEILING)
        if duration > ceiling:
            duration = float(ceiling)
            flags.append("duration_clamped")

        minutes = duration / 60.0

        parsed_temp = _to_float(temp_f)
        temp_range = ACTIVITY_TEMP_RANGES.get(activity_name)
        temp_default = ACTIVITY_TEMP_DEFAULTS.get(activity_name)
        if (
            parsed_temp is None
            or parsed_temp == 0.0
            or (
                temp_range is not None
                and (parsed_temp < temp_range[0] or parsed_temp > temp_range[1])
            )
        ):
            if temp_default is not None:
                temp_f_used = float(temp_default)
                flags.append("temp_defaulted")
            else:
                # Unknown activity: keep a parseable temp if we have one, else 0.
                temp_f_used = None if parsed_temp is None else float(parsed_temp)
                if parsed_temp is None or parsed_temp == 0.0:
                    flags.append("temp_defaulted")
                    temp_f_used = 0.0
        else:
            temp_f_used = float(parsed_temp)

        t_c = (temp_f_used - 32.0) * 5.0 / 9.0

        profile = build_user_profile(
            user_height=user_height,
            user_weight=user_weight,
            gender=gender,
            date_of_birth=date_of_birth,
            unit_of_measure=unit_of_measure,
            as_of=as_of,
        )
        flags.extend(profile["flags"])
        rmr_kcal_min = profile["rmr_kcal_min"]

        if multiplier_forced is not None:
            m = multiplier_forced
        elif activity_name in _COLD_FAMILY:
            m = cold_multiplier(t_c)
        elif activity_name in _HOT_WATER_FAMILY:
            m = hot_multiplier(t_c)
        elif activity_name in _Q10_FAMILY:
            m, _dTc = q10_values(
                t_c, minutes, steam=(activity_name == "Steam Room")
            )
        else:
            m = 1.0

        if activity_name == "Cold Shower":
            net_kcal = SHOWER_ATTENUATION * (m - 1.0) * rmr_kcal_min * minutes
            total_kcal = rmr_kcal_min * minutes + net_kcal
        else:
            net_kcal = (m - 1.0) * rmr_kcal_min * minutes
            total_kcal = m * rmr_kcal_min * minutes

        calories = int(math.floor(total_kcal + 0.5))
        if calories < MIN_CALORIES:
            calories = MIN_CALORIES
            flags.append("min_floor_applied")

        _log_flags(flags)
        return _result(
            calories=calories,
            total_kcal=total_kcal,
            net_kcal=net_kcal,
            multiplier=m,
            rmr_kcal_min=rmr_kcal_min,
            minutes=minutes,
            temp_f_used=temp_f_used,
            activity_type=activity_name,
            confidence=confidence,
            fallback_used=False,
            flags=flags,
        )
    except Exception:
        logger.warning("calorie model exception; returning default", exc_info=True)
        return _fallback_result(flag="exception", activity_type=activity_type)
