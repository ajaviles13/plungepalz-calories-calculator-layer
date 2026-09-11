# plungepalz-calories-calculator-layer

Python 3.14 AWS Lambda layer that estimates calorie burn for five contrast-therapy
activity types: Cold Plunge, Sauna, Cold Shower, Hot Tub, and Steam Room.

The package is **stdlib-only**. `boto3` is imported lazily inside
`fetch_user_profile_fields` so the model stays importable in a bare test
environment. `estimate_calories()` never raises; any failure returns
`calories = 15` with `fallback_used = True`.

Lambda adds `/opt/python` to `sys.path`, so consuming functions import:

```python
from plungepalz_calories import estimate_calories
```

## Local development

```bash
git clone https://github.com/ajaviles13/plungepalz-calories-calculator-layer.git
cd plungepalz-calories-calculator-layer
python -m pip install pytest
python -m pytest tests/ -q
./build_layer.sh
```

`pyproject.toml` sets `pythonpath = ["python"]` for pytest. The built zip is
`plungepalz_calories_layer.zip` (gitignored; regenerate with `./build_layer.sh`).

```
python/plungepalz_calories/   # layer package (stdlib only)
tests/                         # pytest suite
build_layer.sh                 # test, then zip python/plungepalz_calories
```

## Public API

```python
from datetime import datetime, timezone
from plungepalz_calories import estimate_calories, build_user_profile

result = estimate_calories(
    activity_type="Cold Plunge",
    temp_f="45.0",            # ActivitiesRecorded.avg_temp, always Fahrenheit
    duration_seconds="78",    # ActivitiesRecorded.s_length
    user_height="5'8\"",
    user_weight="150.0 lbs",
    gender="",
    date_of_birth="1971-06-04",
    unit_of_measure="Imperial",
    as_of=datetime(2026, 9, 10, tzinfo=timezone.utc),
)

# result["calories"] is an int — write it straight to DynamoDB (no Decimal wrap)
# 7 kcal for the 78-second 45 F plunge above
```

`estimate_calories` returns:

| Key | Type | Notes |
|---|---|---|
| `calories` | `int` | TOTAL kcal, the value written to `ActivitiesRecorded.calories` |
| `total_kcal` | `float` | Unrounded total |
| `net_kcal` | `float` | Unrounded kcal above RMR (not persisted today) |
| `multiplier` | `float` | Metabolic multiplier `m` |
| `rmr_kcal_min` | `float` | Mifflin-St Jeor RMR / 1440 |
| `minutes` | `float` | Duration after any ceiling clamp |
| `temp_f_used` | `float` | Temperature after sanitization |
| `activity_type` | `str` | Canonical name, or the raw string if unknown |
| `model_version` | `str` | Currently `"1.0.0"` |
| `confidence` | `str` | `"high"` \| `"medium"` \| `"low"` \| `"unknown"` |
| `fallback_used` | `bool` | `True` only for exception / invalid duration |
| `flags` | `list[str]` | Substitutions applied |

`net_kcal` is computed and returned but **not** persisted. Switching the
displayed figure later is a one-line change instead of a data backfill.

Also exported: `build_user_profile`, `parse_height_cm`, `parse_weight_kg`,
`age_from_dob`, `fetch_user_profile_fields`, `DEFAULT_CALORIES`, `MODEL_VERSION`.

## Build

```bash
python -m pytest tests/ -q
./build_layer.sh
```

The zip contains `python/plungepalz_calories/*.py` and nothing else. Attach it
to the four PlungePalz Lambdas as a layer.

## Integration (do not call `fetch_user_profile_fields` on the write path)

All three write-path Lambdas already query `accountId-index` on
`UserData_PlungePals`. Extend the existing `ProjectionExpression` — **zero
additional DynamoDB reads**. Only the dispatcher recalculation path should call
`fetch_user_profile_fields`.

### `SmartWatchActivitySaved_Garmin`

Extend `get_user_data()`'s projection from
`'avatar, verified, trophyImage, isAccountPublic'` to also include
`userHeight, userWeight, gender, dateOfBirth, unitOfMeasure`, then replace
`'calories': activity_calories` in the item dict with the model result.
The Garmin device value (`body['ActivityCalories']`) is discarded; optionally
keep it as a separate `calories_device` attribute for comparison.

```python
from plungepalz_calories import estimate_calories

# ProjectionExpression becomes:
# 'avatar, verified, trophyImage, isAccountPublic, userHeight, userWeight, gender, dateOfBirth, unitOfMeasure'

result = estimate_calories(
    activity_type=activity_type,
    temp_f=avg_temp,
    duration_seconds=s_length,
    user_height=user_data.get("userHeight"),
    user_weight=user_data.get("userWeight"),
    gender=user_data.get("gender"),
    date_of_birth=user_data.get("dateOfBirth"),
    unit_of_measure=user_data.get("unitOfMeasure"),
)
item["calories"] = result["calories"]
item["calories_device"] = body.get("ActivityCalories")  # optional
```

### `SmartWatchActivitySaved_AppleWatch`

Same projection change to its `get_user_data()`. Note that
`calories = body.get('calories', 15)` at line ~410 is currently parsed and then
never written to the item; replace it with the model result and add `calories`
to the item dict.

```python
from plungepalz_calories import estimate_calories

result = estimate_calories(
    activity_type=activity_type,
    temp_f=avg_temp,
    duration_seconds=s_length,
    user_height=user_data.get("userHeight"),
    user_weight=user_data.get("userWeight"),
    gender=user_data.get("gender"),
    date_of_birth=user_data.get("dateOfBirth"),
    unit_of_measure=user_data.get("unitOfMeasure"),
)
item["calories"] = result["calories"]
```

### `saveOrEditSessionInAWS`

Extend the projection inside `enhance_payload_with_user_data()`, then set
`payload["calories"]` before `create_record()`. This runs on the `CREATE`
branch only.

```python
from plungepalz_calories import estimate_calories

# Inside enhance_payload_with_user_data(), after the user-data query:
result = estimate_calories(
    activity_type=payload.get("activityType"),
    temp_f=payload.get("avg_temp"),
    duration_seconds=payload.get("s_length"),
    user_height=user_data.get("userHeight"),
    user_weight=user_data.get("userWeight"),
    gender=user_data.get("gender"),
    date_of_birth=user_data.get("dateOfBirth"),
    unit_of_measure=user_data.get("unitOfMeasure"),
)
payload["calories"] = result["calories"]
```

### `SessionRecorded_DispatcherLambda`

Handles recalculation on edit. In the `MODIFY` branch, compare `avg_temp`,
`s_length`, and `activityType` between `OldImage` and `NewImage` using the
existing `get_stream_value()` helper. If any of the three changed, call
`fetch_user_profile_fields(userAccountId)`, recompute, and `update_item` on
`ActivitiesRecorded` setting only `calories`.

Two things to get right:

- `ActivitiesRecorded` has a **composite key** — the update needs
  `Key={"ActivityID": ..., "timestamp": ...}`, both available from
  `record['dynamodb']['Keys']`.
- The write triggers another `MODIFY` event. That second pass sees `avg_temp`,
  `s_length`, and `activityType` unchanged, so it does not recalculate and the
  loop terminates naturally. Do **not** add a recalculation trigger on the
  `calories` attribute itself.

```python
from plungepalz_calories import estimate_calories, fetch_user_profile_fields

if event_name == "MODIFY":
    old_temp = get_stream_value(old_image, "avg_temp")
    new_temp = get_stream_value(new_image, "avg_temp")
    old_len = get_stream_value(old_image, "s_length")
    new_len = get_stream_value(new_image, "s_length")
    old_type = get_stream_value(old_image, "activityType")
    new_type = get_stream_value(new_image, "activityType")

    if (old_temp, old_len, old_type) != (new_temp, new_len, new_type):
        profile = fetch_user_profile_fields(user_account_id)
        result = estimate_calories(
            activity_type=new_type,
            temp_f=new_temp,
            duration_seconds=new_len,
            user_height=profile.get("userHeight"),
            user_weight=profile.get("userWeight"),
            gender=profile.get("gender"),
            date_of_birth=profile.get("dateOfBirth"),
            unit_of_measure=profile.get("unitOfMeasure"),
        )
        keys = record["dynamodb"]["Keys"]
        table.update_item(
            Key={
                "ActivityID": keys["ActivityID"]["S"],
                "timestamp": keys["timestamp"]["S"],
            },
            UpdateExpression="SET calories = :c",
            ExpressionAttributeValues={":c": result["calories"]},
        )
```

## Coefficient table

| Family | Activities | Source | What the coefficient encodes |
|---|---|---|---|
| Cold immersion | Cold Plunge, Cold Shower | Šrámek 2000; shivering ceiling Eyolfson 2001 | Piecewise MET vs water temperature; plunge uses the measured curve; shower applies `SHOWER_ATTENUATION = 0.35` to net only (documented assumption, not measured) |
| Hot water | Hot Tub | Faulkner 2017 | +79% energy expenditure at 40 °C vs thermoneutral 35 °C (`HOT_SLOPE = 0.158`), capped at 2.1 |
| Passive heat | Sauna, Steam Room | Q10 / van't Hoff | 10% metabolic rise per 1 °C modeled core-temp increase; steam adds a +20 °C humidity offset before dTc; `HEAT_MAX_MULTIPLIER = 1.25` |

RMR is Mifflin-St Jeor (1990). Temperature sanitization ranges and defaults
mirror `SmartWatchActivitySaved_Garmin.py` and must stay in sync.

## Fallback matrix

| Condition | `calories` | `fallback_used` | flag |
|---|---|---|---|
| Any uncaught exception | 15 | `True` | `"exception"` |
| `duration_seconds` missing / `<= 0` / unparseable | 15 | `True` | `"invalid_duration"` |
| Unknown `activity_type` | computed at `m = 1.0` | `False` | `"unknown_activity_type"` |
| `temp_f` missing or out of range | computed with activity default | `False` | `"temp_defaulted"` |
| Height / weight / DOB / gender blank | computed with defaults | `False` | `"default_height"` etc. |
| Computed total rounds below 1 | 1 | `False` | `"min_floor_applied"` |

Rounding is round-half-up (`int(math.floor(value + 0.5))`) to match JavaScript
`.toFixed(0)`. Do not use Python's `round()`.

## Model versioning

`MODEL_VERSION` (`"1.0.0"`) should be bumped whenever a coefficient changes.
Stored `calories` values carry no version stamp and cannot be distinguished
after the fact. A bump is the only way to know which sessions were written
under which formula.
