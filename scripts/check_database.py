#!/usr/bin/env python3
"""
Check Database Status

Shows the current state of the trading system database.
Usage: python scripts/check_database.py [--full]

Options:
  --full    Show all tables with more detail
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent


def format_timestamp(ts: str) -> str:
    """Format timestamp for display."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace(" ", "T"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts[:16] if len(ts) > 16 else ts


def main():
    parser = argparse.ArgumentParser(description="Check Database Status")
    parser.add_argument("--full", action="store_true", help="Show full details")
    args = parser.parse_args()

    db_path = project_root / "data" / "agent.db"

    if not db_path.exists():
        print("❌ Database not found. Initialize first:")
        print("   sqlite3 data/agent.db < data/init_schema.sql")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 60)
    print("Database Status")
    print("=" * 60)

    # Portfolio Snapshot
    print("\n📊 PORTFOLIO")
    print("-" * 40)
    cursor.execute("""
        SELECT id, import_timestamp, total_equity, cash_balance
        FROM portfolio_snapshot
        ORDER BY import_timestamp DESC
        LIMIT 1
    """)
    snapshot = cursor.fetchone()

    if snapshot:
        print(f"  Latest Snapshot: #{snapshot['id']}")
        print(f"  Imported: {format_timestamp(snapshot['import_timestamp'])}")
        print(f"  Total Equity: ${snapshot['total_equity']:,.2f}")
        print(f"  Cash Balance: ${snapshot['cash_balance']:,.2f}")

        cursor.execute("""
            SELECT symbol, quantity, current_value
            FROM holdings
            WHERE snapshot_id = ?
            ORDER BY current_value DESC
        """, (snapshot['id'],))
        holdings = cursor.fetchall()
        print(f"  Holdings: {len(holdings)} positions")

        if args.full and holdings:
            print()
            for h in holdings:
                print(f"    {h['symbol']:<6} {h['quantity']:>8,.2f} shares  ${h['current_value']:>10,.2f}")
    else:
        print("  ⚪ No portfolio imported yet")
        print("     Run: python scripts/import_portfolio.py")

    # Strategy Recommendations
    print("\n🎯 RECOMMENDATIONS")
    print("-" * 40)
    cursor.execute("""
        SELECT symbol, action, confidence, reasoning, timestamp
        FROM strategy_recommendations
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    recs = cursor.fetchall()

    if recs:
        print(f"  Recent: {len(recs)} (showing last 5)")
        print()
        for r in recs:
            action_icon = "🟢" if r['action'] == 'BUY' else "🔴" if r['action'] == 'SELL' else "⚪"
            conf = f"{r['confidence']*100:.0f}%" if r['confidence'] else "N/A"
            print(f"    {action_icon} {r['symbol']:<6} {r['action']:<4} {conf:>4}  {format_timestamp(r['timestamp'])}")
            if args.full and r['reasoning']:
                reason = r['reasoning'][:60] + "..." if len(r['reasoning']) > 60 else r['reasoning']
                print(f"       └─ {reason}")
    else:
        print("  ⚪ No recommendations yet")
        print("     Run: python src/main_orchestrator.py --mode market")

    # Risk Decisions
    print("\n🛡️  RISK DECISIONS")
    print("-" * 40)
    cursor.execute("""
        SELECT symbol, action, approved, reason, timestamp
        FROM risk_decisions
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    decisions = cursor.fetchall()

    if decisions:
        approved_count = sum(1 for d in decisions if d['approved'])
        print(f"  Recent: {len(decisions)} ({approved_count} approved)")
        print()
        for d in decisions:
            status = "✅" if d['approved'] else "❌"
            reason = d['reason'][:40] + "..." if len(d['reason']) > 40 else d['reason']
            print(f"    {status} {d['symbol']:<6} {d['action']:<4} {reason}")
    else:
        print("  ⚪ No risk decisions yet")

    # Screener Results
    print("\n🔍 SCREENER")
    print("-" * 40)
    cursor.execute("""
        SELECT symbol, source, rank, screening_timestamp
        FROM screener_results
        ORDER BY rank
        LIMIT 10
    """)
    screened = cursor.fetchall()

    if screened:
        cursor.execute("SELECT COUNT(*) FROM screener_results")
        total = cursor.fetchone()[0]
        print(f"  Cached: {total} symbols (top 10 shown)")
        print(f"  Source: {screened[0]['source'] if screened else 'N/A'}")
        print(f"  Updated: {format_timestamp(screened[0]['screening_timestamp']) if screened else 'N/A'}")
        print()
        symbols = [s['symbol'] for s in screened]
        print(f"    Top 10: {', '.join(symbols)}")
    else:
        print("  ⚪ No screening results cached")
        print("     Run: python scripts/test_screener.py")

    # News Analysis
    print("\n📰 NEWS ANALYSIS")
    print("-" * 40)
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
               SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative,
               SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) as neutral
        FROM news_analysis
        WHERE timestamp > datetime('now', '-24 hours')
    """)
    news = cursor.fetchone()

    if news and news['total'] > 0:
        print(f"  Last 24h: {news['total']} articles analyzed")
        print(f"    🟢 Positive: {news['positive']}")
        print(f"    🔴 Negative: {news['negative']}")
        print(f"    ⚪ Neutral: {news['neutral']}")
    else:
        print("  ⚪ No news analyzed in last 24h")

    # Market Data Cache
    print("\n📈 MARKET DATA CACHE")
    print("-" * 40)
    cursor.execute("""
        SELECT COUNT(DISTINCT symbol) as symbols,
               MAX(timestamp) as latest
        FROM market_data
        WHERE timestamp > datetime('now', '-1 hour')
    """)
    market = cursor.fetchone()

    if market and market['symbols'] > 0:
        print(f"  Symbols cached (last hour): {market['symbols']}")
        print(f"  Latest update: {format_timestamp(market['latest'])}")
    else:
        print("  ⚪ No recent market data cached")
        print("     Run: python scripts/test_market_data.py")

    conn.close()

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
