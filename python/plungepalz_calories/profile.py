"""Height/weight/age/sex parsing and Mifflin-St Jeor RMR.

Never raises. Blank or unparseable fields are replaced with documented defaults
and recorded as flags.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from .constants import (
    AGE_BOUNDS,
    DEFAULT_AGE_YEARS,
    DEFAULT_HEIGHT_STRING,
    DEFAULT_SEX,
    DEFAULT_WEIGHT_STRING,
    HEIGHT_CM_BOUNDS,
    IN_TO_CM,
    LB_TO_KG,
    MIN_RMR_KCAL_DAY,
    SEX_CONSTANT,
    WEIGHT_KG_BOUNDS,
)

logger = logging.getLogger(__name__)

_HEIGHT_FT_IN_RE = re.compile(
    r"""
    ^\s*
    (?P<feet>\d+(?:\.\d+)?)
    \s*'
    \s*
    (?P<inches>\d+(?:\.\d+)?)?
    \s*"?
    \s*$
    """,
    re.VERBOSE,
)
_BARE_NUMBER_RE = re.compile(r"^\s*[+-]?\d+(?:\.\d+)?\s*$")
_CM_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*cms?\s*$", re.IGNORECASE)
_LB_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*lbs?\s*$", re.IGNORECASE)
_KG_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*kgs?\s*$", re.IGNORECASE)
_DOB_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

_BLANK_TOKENS = frozenset({"", "n/a", "na", "none", "null", "unknown"})


def _is_blank(raw) -> bool:
    if raw is None:
        return True
    text = str(raw).strip()
    return text == "" or text.lower() in _BLANK_TOKENS


def _default_height_cm() -> float:
    cm, _flag = _parse_imperial_height(DEFAULT_HEIGHT_STRING)
    return cm if cm is not None else 180.34


def _default_weight_kg() -> float:
    kg, _flag = _parse_weight_from_string(DEFAULT_WEIGHT_STRING, unit_of_measure=None)
    return kg if kg is not None else (160.0 * LB_TO_KG)


def _parse_imperial_height(text: str):
    """Parse a feet/inches string. Returns (cm, None) or (None, flag)."""
    if "'" not in text and '"' not in text:
        return None, None
    match = _HEIGHT_FT_IN_RE.match(text)
    if not match:
        return None, "default_height"
    feet = float(match.group("feet"))
    inches_raw = match.group("inches")
    inches = float(inches_raw) if inches_raw is not None else 0.0
    cm = (feet * 12.0 + inches) * IN_TO_CM
    return cm, None


def parse_height_cm(raw, unit_of_measure=None):
    """Return ``(height_cm, flag)``. ``flag`` is None when the input was used as-is."""
    default_cm = _default_height_cm()
    try:
        if _is_blank(raw):
            return default_cm, "default_height"

        text = str(raw).strip()

        if "'" in text or '"' in text:
            cm, flag = _parse_imperial_height(text)
            if cm is None:
                return default_cm, flag or "default_height"
        elif _CM_RE.match(text):
            cm = float(_CM_RE.match(text).group(1))
        elif _BARE_NUMBER_RE.match(text):
            value = float(text)
            uom = (unit_of_measure or "").strip().lower()
            if uom == "metric":
                cm = value
            elif uom == "imperial":
                cm = value * IN_TO_CM
            else:
                return default_cm, "default_height"
        else:
            return default_cm, "default_height"

        lo, hi = HEIGHT_CM_BOUNDS
        if cm < lo or cm > hi:
            return default_cm, "height_out_of_bounds"
        return float(cm), None
    except Exception:
        return default_cm, "default_height"


def _parse_weight_from_string(text: str, unit_of_measure=None):
    lb_match = _LB_RE.match(text)
    if lb_match:
        return float(lb_match.group(1)) * LB_TO_KG, None
    kg_match = _KG_RE.match(text)
    if kg_match:
        return float(kg_match.group(1)), None
    if _BARE_NUMBER_RE.match(text):
        value = float(text)
        uom = (unit_of_measure or "").strip().lower()
        if uom == "metric":
            return value, None
        if uom == "imperial":
            return value * LB_TO_KG, None
        return None, "default_weight"
    return None, "default_weight"


def parse_weight_kg(raw, unit_of_measure=None):
    """Return ``(weight_kg, flag)``. ``flag`` is None when the input was used as-is."""
    default_kg = _default_weight_kg()
    try:
        if _is_blank(raw):
            return default_kg, "default_weight"

        text = str(raw).strip()
        kg, flag = _parse_weight_from_string(text, unit_of_measure=unit_of_measure)
        if kg is None:
            return default_kg, flag or "default_weight"

        lo, hi = WEIGHT_KG_BOUNDS
        if kg < lo or kg > hi:
            return default_kg, "weight_out_of_bounds"
        return float(kg), None
    except Exception:
        return default_kg, "default_weight"


def _as_of_date(as_of=None) -> date:
    if as_of is None:
        return datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        return as_of.astimezone(timezone.utc).date()
    if isinstance(as_of, date):
        return as_of
    return datetime.now(timezone.utc).date()


def _anniversary_this_year(born: date, year: int) -> date:
    try:
        return born.replace(year=year)
    except ValueError:
        # Feb 29 in a non-leap year: treat the anniversary as March 1.
        return date(year, 3, 1)


def age_from_dob(dob, as_of=None):
    """Return ``(age_years, flag)`` as whole years at ``as_of``."""
    try:
        if _is_blank(dob):
            return DEFAULT_AGE_YEARS, "default_age"

        text = str(dob).strip()
        match = _DOB_RE.match(text)
        if not match:
            return DEFAULT_AGE_YEARS, "default_age"

        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            born = date(year, month, day)
        except ValueError:
            return DEFAULT_AGE_YEARS, "default_age"

        today = _as_of_date(as_of)
        if born > today:
            return DEFAULT_AGE_YEARS, "default_age"

        anniversary = _anniversary_this_year(born, today.year)
        years = today.year - born.year
        if today < anniversary:
            years -= 1

        lo, hi = AGE_BOUNDS
        if years < lo or years > hi:
            return DEFAULT_AGE_YEARS, "age_out_of_bounds"
        return int(years), None
    except Exception:
        return DEFAULT_AGE_YEARS, "default_age"


def parse_sex(raw):
    """Return ``(sex, flag)`` where sex is ``\"male\"`` or ``\"female\"``."""
    try:
        if _is_blank(raw):
            return DEFAULT_SEX, "default_sex"
        text = str(raw).strip().lower()
        if text == "male":
            return "male", None
        if text == "female":
            return "female", None
        return DEFAULT_SEX, "default_sex"
    except Exception:
        return DEFAULT_SEX, "default_sex"


def build_user_profile(
    user_height=None,
    user_weight=None,
    gender=None,
    date_of_birth=None,
    unit_of_measure=None,
    as_of=None,
) -> dict:
    """Build a sanitized anthropometric profile. Never raises."""
    flags = []
    try:
        height_cm, height_flag = parse_height_cm(user_height, unit_of_measure)
        if height_flag:
            flags.append(height_flag)

        weight_kg, weight_flag = parse_weight_kg(user_weight, unit_of_measure)
        if weight_flag:
            flags.append(weight_flag)

        age_years, age_flag = age_from_dob(date_of_birth, as_of=as_of)
        if age_flag:
            flags.append(age_flag)

        sex, sex_flag = parse_sex(gender)
        if sex_flag:
            flags.append(sex_flag)

        rmr_kcal_day = (
            10.0 * weight_kg
            + 6.25 * height_cm
            - 5.0 * age_years
            + SEX_CONSTANT[sex]
        )
        rmr_kcal_day = max(rmr_kcal_day, MIN_RMR_KCAL_DAY)
        rmr_kcal_min = rmr_kcal_day / 1440.0

        return {
            "height_cm": float(height_cm),
            "weight_kg": float(weight_kg),
            "age_years": int(age_years),
            "sex": sex,
            "rmr_kcal_day": float(rmr_kcal_day),
            "rmr_kcal_min": float(rmr_kcal_min),
            "flags": flags,
        }
    except Exception:
        logger.warning("build_user_profile failed; using full defaults", exc_info=True)
        height_cm = _default_height_cm()
        weight_kg = _default_weight_kg()
        rmr_kcal_day = max(
            10.0 * weight_kg
            + 6.25 * height_cm
            - 5.0 * DEFAULT_AGE_YEARS
            + SEX_CONSTANT[DEFAULT_SEX],
            MIN_RMR_KCAL_DAY,
        )
        return {
            "height_cm": float(height_cm),
            "weight_kg": float(weight_kg),
            "age_years": int(DEFAULT_AGE_YEARS),
            "sex": DEFAULT_SEX,
            "rmr_kcal_day": float(rmr_kcal_day),
            "rmr_kcal_min": float(rmr_kcal_day / 1440.0),
            "flags": flags or ["exception"],
        }
