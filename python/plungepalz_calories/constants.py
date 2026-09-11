MODEL_VERSION = "1.0.0"
DEFAULT_CALORIES = 15          # returned whenever the model cannot produce a value
MIN_CALORIES = 1               # floor for any session with duration > 0

# --- Anthropometric defaults (used when the user's profile field is blank/garbage) ---
DEFAULT_HEIGHT_STRING = "5'11\""     # 180.34 cm
DEFAULT_WEIGHT_STRING = "160.0 lbs"  # 72.5747 kg
DEFAULT_AGE_YEARS = 40
DEFAULT_SEX = "male"                 # gender blank/null/unrecognized -> Male

# --- Sanity bounds for parsed anthropometrics (outside -> use default + flag) ---
HEIGHT_CM_BOUNDS = (100.0, 250.0)
WEIGHT_KG_BOUNDS = (30.0, 300.0)
AGE_BOUNDS = (13, 100)
MIN_RMR_KCAL_DAY = 800.0             # floor, guards against absurd RMR

# --- Unit conversion ---
LB_TO_KG = 0.453592
IN_TO_CM = 2.54

# --- Mifflin-St Jeor sex constants ---
SEX_CONSTANT = {"male": 5.0, "female": -161.0}

# --- Temperature sanitization. These MIRROR the deployed constants in ---
# --- SmartWatchActivitySaved_Garmin.py. Keep them in sync.             ---
ACTIVITY_TEMP_RANGES = {
    "Cold Plunge": (23.0, 65.0),
    "Sauna":       (120.0, 220.0),
    "Cold Shower": (23.0, 65.0),
    "Hot Tub":     (90.0, 107.0),
    "Steam Room":  (90.0, 130.0),
}
ACTIVITY_TEMP_DEFAULTS = {
    "Cold Plunge": 50.0,
    "Sauna":       170.0,
    "Cold Shower": 50.0,
    "Hot Tub":     102.0,
    "Steam Room":  110.0,
}

# --- Duration ceilings in seconds (no lower bound — short sessions scale linearly to zero) ---
MAX_DURATION_SECONDS = {
    "Cold Plunge": 1800,
    "Cold Shower": 1800,
    "Sauna":       3600,
    "Steam Room":  3600,
    "Hot Tub":     3600,
}

# --- Cold-immersion family (Šrámek 2000 anchors; Eyolfson 2001 shivering ceiling) ---
COLD_THERMONEUTRAL_C  = 35.0
COLD_MILD_SLOPE       = 0.062   # 35 C -> m=1.00 ; 20 C -> 1.93
COLD_STEEP_BREAK_C    = 20.0
COLD_STEEP_BASE_M     = 1.93
COLD_STEEP_SLOPE      = 0.428   # 20 C -> 1.93 ; 14 C -> 4.50
COLD_MAX_MULTIPLIER   = 4.9     # measured peak shivering ceiling
COLD_WATER_FLOOR_C    = 0.0     # 32 F — water below this is frozen

# --- Cold shower attenuation (documented assumption, not measured) ---
SHOWER_ATTENUATION = 0.35

# --- Hot-water family (Faulkner 2017: +79% EE at 40 C) ---
HOT_THERMONEUTRAL_C   = 35.0
HOT_SLOPE             = 0.158   # 35 C -> 1.00 ; 40 C -> 1.79
HOT_MAX_MULTIPLIER    = 2.1     # ~106 F safety ceiling

# --- Q10 heat family (sauna / steam) ---
Q10_DTC_COEFFICIENT   = 0.001   # dTc = COEFF * (T_C - 25) * minutes
Q10_DTC_BASELINE_C    = 25.0
Q10_DTC_MAX           = 2.5     # physiological/safety ceiling on core-temp rise
Q10_PER_DEGREE        = 0.10    # 10% metabolic rise per 1 C core temp (lit. band 0.07-0.13)
STEAM_HUMIDITY_OFFSET_C = 20.0  # 100% RH -> dry-sauna-equivalent air temperature
HEAT_MAX_MULTIPLIER   = 1.25    # sanity cap

CONFIDENCE = {
    "Cold Plunge": "high",     # Šrámek 2000, measured
    "Hot Tub":     "high",     # Faulkner 2017, measured
    "Sauna":       "medium",   # Q10 sound, core-temp rise modeled
    "Steam Room":  "medium",   # humidity offset derived, not measured
    "Cold Shower": "low",      # scaling assumption
}
