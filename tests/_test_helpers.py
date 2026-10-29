"""
Varsha — Test Helper Functions

Core event detection algorithms used by both tests and the main pipeline.
These are the reference implementations — keep them pure functions.
"""


def detect_onset(rainfall, min_rain=20, consecutive_days=3):
    """
    Detect agronomic onset in a daily rainfall time series.

    Args:
        rainfall: List of daily rainfall values (mm)
        min_rain: Minimum accumulated rainfall for onset (mm)
        consecutive_days: Number of consecutive days required

    Returns:
        Index (0-based) of onset day, or None if no onset detected
    """
    for i in range(len(rainfall) - consecutive_days + 1):
        window_rain = sum(rainfall[i:i + consecutive_days])
        if window_rain >= min_rain:
            return i
    return None


def detect_false_onset(rainfall, onset_day, dry_threshold=2.5, min_dry_days=7, window=30):
    """
    Check if a detected onset is a false onset.

    A false onset occurs when the onset criterion is met but is followed
    by a dry spell of >= min_dry_days within the verification window.

    Args:
        rainfall: List of daily rainfall values (mm)
        onset_day: Index of onset day (0-based)
        dry_threshold: Rain below this counts as dry (mm)
        min_dry_days: Minimum dry spell length to trigger false onset
        window: Verification window after onset (days)

    Returns:
        Tuple: (is_false_onset, dry_spell_start_index, dry_spell_length)
    """
    if onset_day is None:
        return False, None, 0

    end = min(onset_day + window, len(rainfall))
    check_start = onset_day + 3  # Skip the onset rain days

    dry_count = 0
    dry_start = None

    for i in range(check_start, end):
        if rainfall[i] < dry_threshold:
            if dry_count == 0:
                dry_start = i
            dry_count += 1
        else:
            if dry_count >= min_dry_days:
                return True, dry_start, dry_count
            dry_count = 0
            dry_start = None

    if dry_count >= min_dry_days:
        return True, dry_start, dry_count

    return False, None, 0


def detect_dry_spells(rainfall, threshold=2.5, min_length=7):
    """
    Find all dry spells in a daily rainfall time series.

    Args:
        rainfall: List of daily rainfall values (mm)
        threshold: Rain below this counts as dry (mm)
        min_length: Minimum dry spell length to report (days)

    Returns:
        List of dicts: [{"start": idx, "length": days}, ...]
    """
    spells = []
    dry_count = 0
    dry_start = None

    for i, rain in enumerate(rainfall):
        if rain < threshold:
            if dry_count == 0:
                dry_start = i
            dry_count += 1
        else:
            if dry_count >= min_length:
                spells.append({"start": dry_start, "length": dry_count})
            dry_count = 0

    # Check trailing dry spell
    if dry_count >= min_length:
        spells.append({"start": dry_start, "length": dry_count})

    return spells


def classify_rainfall_day(rainfall_mm, thresholds=None):
    """
    Classify a day's rainfall according to IMD categories.

    Returns:
        dict with boolean flags
    """
    if thresholds is None:
        thresholds = {
            "rainy_day": 2.5,
            "heavy": 64.5,
            "very_heavy": 115.6,
            "extremely_heavy": 204.5,
        }

    return {
        "is_rainy_day": rainfall_mm >= thresholds["rainy_day"],
        "is_heavy_rain": rainfall_mm >= thresholds["heavy"],
        "is_very_heavy_rain": rainfall_mm >= thresholds["very_heavy"],
        "is_extremely_heavy_rain": rainfall_mm >= thresholds["extremely_heavy"],
    }
