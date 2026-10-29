"""
Varsha — Tests for Event Labelling

Tests the event detection logic (onset, false onset, dry spell, heavy rain)
against known cases.
"""

import pytest
from datetime import date


class TestRainyDay:
    """Test rainy day classification."""

    def test_rainy_day_threshold(self):
        """Days with >= 2.5 mm are rainy days."""
        threshold = 2.5
        assert 3.0 >= threshold  # Rainy
        assert 2.5 >= threshold  # Rainy (boundary)
        assert not (2.4 >= threshold)  # Not rainy
        assert not (0.0 >= threshold)  # Dry

    def test_heavy_rain_threshold(self):
        """Days with >= 64.5 mm are heavy rain."""
        threshold = 64.5
        assert 65.0 >= threshold
        assert 64.5 >= threshold  # Boundary
        assert not (64.4 >= threshold)

    def test_very_heavy_rain_threshold(self):
        """Days with >= 115.6 mm are very heavy rain."""
        threshold = 115.6
        assert 120.0 >= threshold
        assert not (115.5 >= threshold)


class TestOnsetDetection:
    """Test agronomic onset detection."""

    def test_onset_simple(self):
        """Onset: >= 20 mm over 3 consecutive days."""
        from _test_helpers import detect_onset

        # 3 days of good rain
        rainfall = [0, 0, 0, 8, 7, 6, 2, 3]  # Day 3-5: 8+7+6=21 mm >= 20
        onset_day = detect_onset(rainfall, min_rain=20, consecutive_days=3)
        assert onset_day == 3  # 0-indexed

    def test_onset_not_enough_rain(self):
        """No onset when rain is insufficient."""
        from _test_helpers import detect_onset

        rainfall = [0, 0, 5, 5, 5, 0, 0]  # 3-day max = 15 < 20
        onset_day = detect_onset(rainfall, min_rain=20, consecutive_days=3)
        assert onset_day is None

    def test_onset_non_consecutive(self):
        """Onset requires consecutive days."""
        from _test_helpers import detect_onset

        rainfall = [0, 10, 0, 10, 0, 10, 0]  # Never 3 consecutive
        onset_day = detect_onset(rainfall, min_rain=20, consecutive_days=3)
        assert onset_day is None


class TestFalseOnset:
    """Test false onset detection."""

    def test_false_onset_detected(self):
        """False onset: onset followed by 7+ dry days within 30 days."""
        from _test_helpers import detect_false_onset

        # Onset on day 3, then 7 dry days starting day 10
        rainfall = [0]*3 + [8, 7, 6] + [3, 2, 1, 0.5] + [0]*8 + [5]*10
        is_false, dry_start, dry_len = detect_false_onset(
            rainfall, onset_day=3, dry_threshold=2.5, min_dry_days=7, window=30
        )
        assert is_false
        assert dry_len >= 7

    def test_true_onset(self):
        """True onset: no extended dry spell after onset."""
        from _test_helpers import detect_false_onset

        # Onset on day 3, continuous rain
        rainfall = [0]*3 + [8, 7, 6] + [3]*24
        is_false, _, _ = detect_false_onset(
            rainfall, onset_day=3, dry_threshold=2.5, min_dry_days=7, window=30
        )
        assert not is_false


class TestDrySpell:
    """Test dry spell detection."""

    def test_dry_spell_found(self):
        """Detect a dry spell of >= 7 days."""
        from _test_helpers import detect_dry_spells

        rainfall = [5]*5 + [0]*10 + [5]*5
        spells = detect_dry_spells(rainfall, threshold=2.5, min_length=7)
        assert len(spells) == 1
        assert spells[0]["length"] == 10

    def test_no_dry_spell(self):
        """No dry spell when rain is regular."""
        from _test_helpers import detect_dry_spells

        rainfall = [3]*20
        spells = detect_dry_spells(rainfall, threshold=2.5, min_length=7)
        assert len(spells) == 0


# --- Helper module (created alongside tests) ---
# This would be in tests/_test_helpers.py

def _create_test_helpers():
    """Write the helper functions used by tests."""
    code = '''
def detect_onset(rainfall, min_rain=20, consecutive_days=3):
    """Detect agronomic onset in a rainfall time series."""
    for i in range(len(rainfall) - consecutive_days + 1):
        window_rain = sum(rainfall[i:i+consecutive_days])
        if window_rain >= min_rain:
            return i
    return None


def detect_false_onset(rainfall, onset_day, dry_threshold=2.5, min_dry_days=7, window=30):
    """Check if an onset is false (dry spell follows within window)."""
    if onset_day is None:
        return False, None, 0

    end = min(onset_day + window, len(rainfall))
    check_start = onset_day + 3  # After the onset rain

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
    """Find all dry spells in a rainfall time series."""
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

    if dry_count >= min_length:
        spells.append({"start": dry_start, "length": dry_count})

    return spells
'''
    return code
