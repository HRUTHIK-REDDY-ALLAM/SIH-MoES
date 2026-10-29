"""
Varsha — Daily Pipeline Orchestrator

Runs the full forecast pipeline:
1. Fetch latest data (rainfall, indices, forecasts)
2. Run event detection
3. Run forecast models
4. Generate advisories
5. Store results in DB

Usage:
    python -m backend.pipeline.daily_run
    # Or via docker compose: docker compose --profile pipeline run pipeline
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("varsha.pipeline")


def run_pipeline(target_date: date = None):
    """
    Execute the daily forecast pipeline.

    Args:
        target_date: Date to run for (default: today).
                     For replay mode, pass historical dates.
    """
    if target_date is None:
        target_date = date.today()

    logger.info(f"{'='*60}")
    logger.info(f"Varsha Daily Pipeline — {target_date}")
    logger.info(f"{'='*60}")

    # Step 1: Fetch latest data
    logger.info("Step 1/5: Fetching data...")
    # TODO: Implement in Milestone 2
    # from data.fetchers import chirps, enso_oni, iod_dmi, mjo_bsiso
    # chirps.fetch_latest(target_date)
    # enso_oni.fetch_latest()
    # iod_dmi.fetch_latest()
    # mjo_bsiso.fetch_latest()
    logger.info("  → Data fetch: SKIPPED (not yet implemented)")

    # Step 2: Event detection
    logger.info("Step 2/5: Event detection...")
    # TODO: Implement in Milestone 3
    # from models.baselines import climatology
    # climatology.label_events(target_date)
    logger.info("  → Event detection: SKIPPED (not yet implemented)")

    # Step 3: Run forecast models
    logger.info("Step 3/5: Running models...")
    # TODO: Implement in Milestone 4
    # from models.downscaling import lgbm_ngboost
    # from models.hmm import regime_model
    # from models.onset import survival_model, false_onset
    logger.info("  → Forecast models: SKIPPED (not yet implemented)")

    # Step 4: Generate advisories
    logger.info("Step 4/5: Generating advisories...")
    # TODO: Implement in Milestone 6
    # from impact import advisory_engine
    # advisory_engine.generate(target_date)
    logger.info("  → Advisory generation: SKIPPED (not yet implemented)")

    # Step 5: Translation & messaging
    logger.info("Step 5/5: Translation & delivery...")
    # TODO: Implement in Milestone 7
    # from translation import adapter
    # from backend.services import messaging
    logger.info("  → Translation & messaging: SKIPPED (not yet implemented)")

    logger.info(f"Pipeline complete for {target_date}")
    logger.info(f"{'='*60}")


def main():
    """Entry point for CLI usage."""
    import argparse
    parser = argparse.ArgumentParser(description="Varsha Daily Pipeline")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Run in replay mode for the entire demo season.",
    )
    args = parser.parse_args()

    if args.replay:
        # Run through the entire 2023 Kharif season
        from datetime import timedelta
        start = date(2023, 5, 15)
        end = date(2023, 10, 15)
        current = start
        while current <= end:
            run_pipeline(current)
            current += timedelta(days=1)
    elif args.date:
        run_pipeline(date.fromisoformat(args.date))
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
