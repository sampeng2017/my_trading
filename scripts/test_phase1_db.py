#!/usr/bin/env python3
"""
Test Phase 1: Database connection adapter.

Verifies that the db_connection module works correctly with both
local SQLite and Turso cloud database modes.

Usage:
    python scripts/test_phase1_db.py
"""
import sys
import os

# Add project paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from dotenv import load_dotenv
load_dotenv()

from src.data.db_connection import get_connection, get_db_mode


def main():
    print("=" * 50)
    print("Phase 1 Database Connection Test")
    print("=" * 50)

    # Check mode
    mode = get_db_mode()
    print(f"\n1. Database Mode: {mode}")

    if mode == 'turso':
        turso_url = os.environ.get('TURSO_DATABASE_URL', '')
        print(f"   Turso URL: {turso_url[:30]}..." if turso_url else "   Turso URL: NOT SET")
        print(f"   Auth Token: {'SET' if os.environ.get('TURSO_AUTH_TOKEN') else 'NOT SET'}")
    else:
        print("   Using local SQLite (data/agent.db)")

    # Test connection
    print("\n2. Testing Connection...")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # List tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"   Found {len(tables)} tables")

            # Count rows in key tables
            print("\n3. Table Row Counts:")
            for table in ['portfolio_snapshot', 'holdings', 'market_data', 'strategy_recommendations']:
                if table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"   {table}: {count} rows")
                else:
                    print(f"   {table}: TABLE NOT FOUND")

            # Test a simple query
            print("\n4. Sample Query (latest snapshot):")
            cursor.execute("""
                SELECT id, import_timestamp, total_equity, cash_balance
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                print(f"   ID: {row[0]}")
                print(f"   Timestamp: {row[1]}")
                print(f"   Total Equity: ${row[2]:,.2f}" if row[2] else "   Total Equity: N/A")
                print(f"   Cash Balance: ${row[3]:,.2f}" if row[3] else "   Cash Balance: N/A")
            else:
                print("   No snapshots found")

        print("\n" + "=" * 50)
        print("SUCCESS: Phase 1 database connection working!")
        print("=" * 50)

    except Exception as e:
        print(f"\n   ERROR: {e}")
        print("\n" + "=" * 50)
        print("FAILED: Check your configuration")
        print("=" * 50)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
