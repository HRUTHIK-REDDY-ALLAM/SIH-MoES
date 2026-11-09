"""
Varsha — Test helpers.

The event-detection reference implementations now live in models/events.py
(used by training, verification and the pipeline). Re-exported here so the
existing tests keep working.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.events import (  # noqa: E402,F401
    classify_rainfall_day,
    detect_dry_spells,
    detect_false_onset,
    detect_onset,
)
