#!/usr/bin/env python3
"""
Scheduled orchestrator runner with market calendar check.

Usage:
    python scripts/run_scheduled.py premarket
    python scripts/run_scheduled.py market
    python scripts/run_scheduled.py postmarket
"""
import os
import sys
from datetime import date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def is_market_open_today() -> bool:
    """Check if US stock market is open today."""
    try:
        import pandas_market_calendars as mcal

        nyse = mcal.get_calendar('NYSE')
        today = date.today()
        schedule = nyse.schedule(start_date=today, end_date=today)

        return len(schedule) > 0

    except ImportError:
        # Fallback: just check if it's a weekday
        return date.today().weekday() < 5  # Mon-Fri


def log_run(mode: str, status: str, error_message: str = None):
    """Log the scheduled run to database."""
    try:
        from src.data.db_connection import get_connection

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'agent.db')

        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO orchestrator_runs (mode, status, started_at, triggered_by, error_message)
                   VALUES (?, ?, datetime('now'), 'scheduled', ?)""",
                (mode, status, error_message)
            )
            conn.commit()
    except Exception as e:
        print(f"Failed to log run: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_scheduled.py <mode>")
        print("Modes: premarket, market, postmarket")
        sys.exit(1)

    mode = sys.argv[1]
    valid_modes = ["premarket", "market", "postmarket"]

    if mode not in valid_modes:
        print(f"Invalid mode: {mode}")
        print(f"Valid modes: {valid_modes}")
        sys.exit(1)

    # Check if market is open
    if not is_market_open_today():
        print(f"Market closed today (weekend or holiday), skipping {mode} run")
        log_run(mode, "skipped", "Market closed")
        sys.exit(0)

    print(f"Starting scheduled {mode} run...")

    try:
        from src.main_orchestrator import TradingOrchestrator

        orchestrator = TradingOrchestrator()
        orchestrator.run(mode=mode)

        print(f"Scheduled {mode} run completed successfully")
        log_run(mode, "completed")

    except Exception as e:
        print(f"Scheduled {mode} run failed: {e}")
        log_run(mode, "failed", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
