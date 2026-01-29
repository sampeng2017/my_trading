#!/usr/bin/env python3
"""
Test Market Data Fetching

Fetches current prices and indicators for test symbols.
Usage: python scripts/test_market_data.py [SYMBOL1 SYMBOL2 ...]

Default symbols: AAPL, MSFT, GOOGL
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from agents.market_analyst import MarketAnalyst


def main():
    db_path = project_root / "data" / "agent.db"

    # Check database exists
    if not db_path.exists():
        print("❌ Database not found. Initialize first:")
        print("   sqlite3 data/agent.db < data/init_schema.sql")
        return 1

    # Get symbols from args or use defaults
    if len(sys.argv) > 1:
        symbols = [s.upper() for s in sys.argv[1:]]
    else:
        symbols = ["AAPL", "MSFT", "GOOGL"]

    print("=" * 60)
    print("Market Data Test")
    print("=" * 60)

    # Show data source info
    alpaca_key = os.getenv("ALPACA_API_KEY")
    if alpaca_key:
        print(f"📡 Data source: Alpaca API (with Yahoo Finance fallback)")
    else:
        print(f"📡 Data source: Yahoo Finance only")

    print(f"🔍 Testing symbols: {', '.join(symbols)}")
    print("-" * 60)

    # Initialize market analyst
    ma = MarketAnalyst(
        str(db_path),
        api_key=os.getenv("ALPACA_API_KEY"),
        api_secret=os.getenv("ALPACA_SECRET_KEY")
    )

    # Fetch data
    print("\nFetching market data...\n")
    data = ma.scan_symbols(symbols)

    if not data:
        print("❌ No data returned. Check your API keys and network connection.")
        return 1

    # Display results
    print(f"{'Symbol':<8} {'Price':>10} {'ATR':>8} {'SMA-50':>10} {'Volume':>12} {'Volatile':>8} {'Source':<12}")
    print("-" * 70)

    for symbol in symbols:
        if symbol in data:
            d = data[symbol]
            price = f"${d['price']:.2f}" if d.get('price') else "N/A"
            atr = f"{d['atr']:.2f}" if d.get('atr') else "N/A"
            sma = f"${d['sma_50']:.2f}" if d.get('sma_50') else "N/A"
            vol = f"{d['avg_volume']:,}" if d.get('avg_volume') else "N/A"
            volatile = "⚠️ Yes" if d.get('is_volatile') else "No"
            source = d.get('source', 'Unknown')
            print(f"{symbol:<8} {price:>10} {atr:>8} {sma:>10} {vol:>12} {volatile:>8} {source:<12}")
        else:
            print(f"{symbol:<8} {'Failed to fetch':^58}")

    print("-" * 70)
    print(f"\n✅ Fetched data for {len(data)}/{len(symbols)} symbols")
    print(f"   Data cached in database for 5 minutes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
