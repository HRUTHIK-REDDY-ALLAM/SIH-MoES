"""
Varsha — LGD Boundaries Fetcher (Stub)

Downloads administrative boundaries from the Local Government Directory (LGD).
https://lgdirectory.gov.in/

For the prototype, we generate synthetic boundaries.
Real boundaries can be obtained from:
1. LGD API (limited)
2. Survey of India
3. DataMeet community (https://github.com/datameet)
4. GADM (https://gadm.org) for district level
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
CACHE_DIR = Path("data/cache/lgd")


def fetch_boundaries(state_code, district_codes=None, cache_dir=CACHE_DIR):
    """Fetch LGD boundaries. Stub — using synthetic boundaries for now."""
    logger.info(f"LGD fetch for state {state_code}: Using SYNTHETIC boundaries")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return None
