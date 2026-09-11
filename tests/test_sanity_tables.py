from datetime import datetime, timezone

from plungepalz_calories import estimate_calories

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)

MALE = dict(
    user_height="5'10\"",
    user_weight="180 lb",
    gender="Male",
    date_of_birth="1986-09-10",
    as_of=AS_OF,
)
FEMALE = dict(
    user_height="5'5\"",
    user_weight="140 lb",
    gender="Female",
    date_of_birth="1986-09-10",
    as_of=AS_OF,
)

# (activity, profile, temp_f, minutes, expected_net, expected_total_or_None)
ROWS = [
    ("Cold Plunge", MALE, 50, 3, 14.0, 17.6),
    ("Cold Plunge", MALE, 50, 5, 23.4, 29.4),
    ("Cold Plunge", MALE, 60, 3, 10.1, 13.7),
    ("Cold Plunge", FEMALE, 50, 3, 10.6, 13.4),
    ("Cold Plunge", FEMALE, 50, 5, 17.7, 22.3),
    ("Cold Shower", MALE, 60, 5, 5.9, None),
    ("Cold Shower", MALE, 50, 3, 4.9, None),
    ("Cold Shower", FEMALE, 60, 5, 4.5, None),
    ("Sauna", MALE, 176, 20, 2.6, 26.7),
    ("Sauna", MALE, 194, 30, 7.0, 43.1),
    ("Sauna", FEMALE, 176, 20, 2.0, 20.1),
    ("Steam Room", MALE, 115, 15, 1.1, 19.0),
    ("Steam Room", MALE, 120, 20, 2.1, 26.2),
    ("Steam Room", FEMALE, 115, 15, 0.8, 14.3),
    ("Hot Tub", MALE, 104, 20, 19.0, 43.1),
    ("Hot Tub", MALE, 102, 30, 22.2, 58.3),
    ("Hot Tub", FEMALE, 104, 20, 14.3, 32.5),
    ("Hot Tub", MALE, 100, 15, 8.0, 26.0),
]


def test_sanity_tables():
    for activity, profile, temp_f, minutes, expected_net, expected_total in ROWS:
        result = estimate_calories(
            activity,
            temp_f,
            minutes * 60.0,
            **profile,
        )
        assert abs(result["net_kcal"] - expected_net) <= 0.2, (
            activity,
            temp_f,
            minutes,
            result["net_kcal"],
        )
        if expected_total is not None:
            assert abs(result["total_kcal"] - expected_total) <= 0.2, (
                activity,
                temp_f,
                minutes,
                result["total_kcal"],
            )
