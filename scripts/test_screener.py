#!/usr/bin/env python3
"""
Test Stock Screener

Runs the stock screener to discover tradeable stocks.
Usage: python scripts/test_screener.py [--max N]

Options:
  --max N    Maximum symbols to return (default: 10)
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from agents.stock_screener import StockScreener
from utils.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Test Stock Screener")
    parser.add_argument("--max", type=int, default=10, help="Max symbols to return")
    args = parser.parse_args()

    db_path = project_root / "data" / "agent.db"

    # Check database exists
    if not db_path.exists():
        print("❌ Database not found. Initialize first:")
        print("   sqlite3 data/agent.db < data/init_schema.sql")
        return 1

    print("=" * 60)
    print("Stock Screener Test")
    print("=" * 60)

    # Show data source info
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpha_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    print("\n📡 Data Sources:")
    if alpaca_key:
        print("  ✅ Alpaca API (primary)")
    else:
        print("  ⚪ Alpaca API not configured")

    if alpha_key:
        print("  ✅ Alpha Vantage (backup)")
    else:
        print("  ⚪ Alpha Vantage not configured")

    if not alpaca_key and not alpha_key:
        print("\n❌ No screener data source configured!")
        print("   Set ALPACA_API_KEY or ALPHA_VANTAGE_API_KEY in .env")
        return 1

    # Load config
    try:
        config = load_config()
    except Exception:
        config = {}

    # Initialize screener
    print(f"\n🔍 Screening for top {args.max} tradeable stocks...")
    print("-" * 60)

    screener = StockScreener(
        db_path=str(db_path),
        alpaca_key=alpaca_key,
        alpaca_secret=os.getenv("ALPACA_SECRET_KEY"),
        alpha_vantage_key=alpha_key,
        config=config
    )

    # Run screening
    symbols = screener.screen_stocks(max_symbols=args.max)

    if not symbols:
        print("❌ No symbols found. Check API keys and try again.")
        return 1

    print(f"\n✅ Found {len(symbols)} tradeable stocks:\n")
    print(f"  {'Rank':<6} {'Symbol':<8}")
    print("  " + "-" * 14)
    for i, symbol in enumerate(symbols, 1):
        print(f"  {i:<6} {symbol:<8}")

    # Show stats
    stats = screener.get_screening_stats()
    if stats.get('last_run'):
        print(f"\n📊 Screening Stats:")
        print(f"  Last run: {stats['last_run']['timestamp']}")
        print(f"  Source: {stats['last_run']['source']}")
        print(f"  Candidates found: {stats['last_run']['found']}")
        print(f"  After filtering: {stats['last_run']['filtered']}")

    print(f"\n💡 These symbols will be added to your monitoring list")
    print(f"   alongside your static watchlist and portfolio holdings.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
