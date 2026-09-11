# plungepalz-calories-calculator-layer

Python 3.14 AWS Lambda layer that estimates calorie burn for five contrast-therapy
activity types: Cold Plunge, Sauna, Cold Shower, Hot Tub, and Steam Room.

The package is **stdlib-only**. `boto3` is imported lazily inside
`fetch_user_profile_fields` so the model stays importable in a bare test
environment. `estimate_calories()` never raises. Calorie estimation is a
**premium-only** feature: `is_premium` must resolve to exactly `True` or the
function returns `calories = 0` without calculating. A confirmed premium user's
calculation failure returns `calories = 15` with `fallback_used = True`.

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
    is_premium=True,          # UserData_PlungePals.isPremium — omit or False -> 0
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
| `confidence` | `str` | `"high"` \| `"medium"` \| `"low"` \| `"unknown"` \| `"gated"` |
| `is_premium` | `bool` | How the premium gate resolved |
| `premium_gated` | `bool` | `True` means the result was suppressed to 0 |
| `fallback_used` | `bool` | `True` only for exception / invalid duration |
| `flags` | `list[str]` | Substitutions applied |

A gated (non-premium) result has the same key set, with `calories = 0`,
`total_kcal = 0.0`, `net_kcal = 0.0`, `multiplier = 0.0`,
`confidence = "gated"`, `premium_gated = True`, and `flags = ["not_premium"]`.
Callers can index the dict unconditionally.

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
only to `SessionRecorded_DispatcherLambda`.

## Premium gate (fail-closed)

`is_premium` is resolved in its own `try/except` **before** any profile parsing
or multiplier work. Only `True` (bool) or a string whose stripped lower form is
`"true"` (plus `1` / `"1"`) counts as premium. `None`, `""`, `False`, a missing
keyword, an unrecognized value, and any exception while resolving all mean
not-premium.

The 15-calorie fallback is reachable **only** after premium was positively
confirmed. A failed DynamoDB lookup, a missing `isPremium` attribute, or an
exception thrown before premium resolves yields 0, never 15. `MIN_CALORIES`
does not lift a gated 0 to 1.

The dispatcher must pass `isPremium` through. If it is omitted the layer treats
the user as non-premium and writes 0 — fail-safe, but it silently disables the
feature, so check that parameter first when debugging an unexpected zero.

## Integration (one call site)

**There is exactly one call site: `SessionRecorded_DispatcherLambda`.** Do not
attach this layer to `saveOrEditSessionInAWS`, `SmartWatchActivitySaved_AppleWatch`,
or `SmartWatchActivitySaved_Garmin`. Those three write the activity record; the
DynamoDB stream on `ActivitiesRecorded` then drives calorie estimation from a
single place, covering the mobile app, both watches, and the watch fail-safe
save paths uniformly.

Do not modify those writer Lambdas except as noted below.

### Hot path

`fetch_user_profile_fields()` runs on **every INSERT**. The dispatcher has no
pre-existing user query. `UserData_PlungePals` is **provisioned at 10 RCU**
(autoscaling 1–10), not on-demand.

- Keep the `ProjectionExpression` minimal (`userHeight`, `userWeight`,
  `gender`, `dateOfBirth`, `unitOfMeasure`, `isPremium`).
- Reuse the module-level `boto3.resource("dynamodb")` handle across warm
  invocations.
- Do not add a retry loop. A failed lookup returns `{}`, which the premium
  gate reads as not-premium and resolves to 0.

### Stream values are strings

`get_stream_value()` returns DynamoDB `N` values as strings, so `temp_f`
arrives as `"45.0"` and `duration_seconds` as `"78"`. The coercion helpers
accept `str` first-class; this is the normal path, not an edge case.

### Recalculation contract

The dispatcher recalculates only when `avg_temp` or `s_length` changes. It
writes only the `calories` attribute, so the resulting MODIFY shows both
inputs unchanged and does not recalculate. The loop terminates after one
bounce. The layer needs no loop protection of its own — do **not** add
`calories` to the recalculation trigger set.

`activityType` is fixed at record creation and is never editable, so it is
not a recalculation trigger. The multiplier family for a given record never
changes after the first calculation.

### Zero is a real write

Non-premium returns a real `0`, not a failure. The dispatcher distinguishes
`None` (calculation could not be attempted, skip the write) from `0`
(premium gate, write it). `estimate_calories()` always returns a dict —
never `None`.

`isPremium` is read live at calculation time, so an edited session reflects
the user's status at edit time rather than at record creation. Subscription
changes alone do not recalculate past records, since `UserData_PlungePals`
has its own stream that nothing here consumes. Intended behavior given there
is no backfill.

### Dispatcher call shape

```python
from plungepalz_calories import estimate_calories, fetch_user_profile_fields

profile = fetch_user_profile_fields(user_account_id)   # {} on failure -> gate resolves to 0

result = estimate_calories(
    activity_type=get_stream_value(new_image, "activityType"),
    temp_f=get_stream_value(new_image, "avg_temp"),
    duration_seconds=get_stream_value(new_image, "s_length"),
    user_height=profile.get("userHeight"),
    user_weight=profile.get("userWeight"),
    gender=profile.get("gender"),
    date_of_birth=profile.get("dateOfBirth"),
    unit_of_measure=profile.get("unitOfMeasure"),
    is_premium=profile.get("isPremium"),
)
calories = int(result["calories"])
```

The write uses the composite key — `ActivitiesRecorded` is partitioned on
`ActivityID` and sorted on `timestamp`, and both are present in
`record["dynamodb"]["Keys"]`:

```python
table.update_item(
    Key={"ActivityID": keys["ActivityID"]["S"], "timestamp": keys["timestamp"]["S"]},
    UpdateExpression="SET #cal = :cal",
    ExpressionAttributeNames={"#cal": "calories"},
    ExpressionAttributeValues={":cal": calories},
)
```

On INSERT the record exists briefly without the final calorie value.
`SmartWatchActivitySaved_Garmin` currently writes `'calories': activity_calories`
(the watch's own estimate, e.g. `2`), which would visibly flip to the model
value a beat later. Remove that line from the Garmin item dict so the
attribute is simply absent until the dispatcher populates it.

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
| `is_premium` not exactly `True` (incl. `None`, `""`, `False`, missing) | 0 | `False` | `"not_premium"` |
| Exception raised **before** premium resolves | 0 | `True` | `"exception"` |
| Premium confirmed, then any uncaught exception | 15 | `True` | `"exception"` |
| Premium confirmed, `duration_seconds` missing / `<= 0` / unparseable | 15 | `True` | `"invalid_duration"` |
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
