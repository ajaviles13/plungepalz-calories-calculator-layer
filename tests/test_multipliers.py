from plungepalz_calories.constants import ACTIVITY_TEMP_RANGES
from plungepalz_calories.model import cold_multiplier, hot_multiplier, q10_values


def test_cold_anchors():
    assert abs(cold_multiplier(35.0) - 1.00) < 0.01
    assert abs(cold_multiplier(20.0) - 1.93) < 0.01
    assert abs(cold_multiplier(14.0) - 4.50) < 0.01
    assert abs(cold_multiplier(10.0) - 4.9) < 0.01
    assert abs(cold_multiplier(0.0) - 4.9) < 0.01


def test_hot_tub_anchors():
    assert abs(hot_multiplier(35.0) - 1.00) < 0.01
    assert abs(hot_multiplier(40.0) - 1.79) < 0.01
    assert abs(hot_multiplier(42.0) - 2.1) < 0.01
    assert abs(hot_multiplier(30.0) - 1.00) < 0.01


def test_q10_sauna_anchors():
    m, dTc = q10_values(80.0, 20.0, steam=False)
    assert abs(dTc - 1.10) < 0.01
    assert abs(m - 1.110) < 0.01

    m, dTc = q10_values(90.0, 30.0, steam=False)
    assert abs(dTc - 1.95) < 0.01
    assert abs(m - 1.195) < 0.01


def test_steam_humidity_offset():
    _m, dTc = q10_values(46.11, 15.0, steam=True)
    assert abs(dTc - 0.617) < 0.01


def _f_to_c(temp_f):
    return (temp_f - 32.0) * 5.0 / 9.0


def test_monotonicity_across_valid_ranges():
    minutes = 20.0
    step = 0.5

    for activity, (lo, hi) in ACTIVITY_TEMP_RANGES.items():
        temps = []
        t = lo
        while t <= hi + 1e-9:
            temps.append(t)
            t += step
        multipliers = []
        for temp_f in temps:
            t_c = _f_to_c(temp_f)
            if activity in ("Cold Plunge", "Cold Shower"):
                multipliers.append(cold_multiplier(t_c))
            elif activity == "Hot Tub":
                multipliers.append(hot_multiplier(t_c))
            else:
                m, _dTc = q10_values(t_c, minutes, steam=(activity == "Steam Room"))
                multipliers.append(m)

        if activity in ("Cold Plunge", "Cold Shower"):
            # Colder water -> equal or higher multiplier.
            for prev, cur in zip(multipliers, multipliers[1:]):
                assert cur <= prev + 1e-12, activity
        else:
            # Hotter air/water -> equal or higher multiplier.
            for prev, cur in zip(multipliers, multipliers[1:]):
                assert cur >= prev - 1e-12, activity
