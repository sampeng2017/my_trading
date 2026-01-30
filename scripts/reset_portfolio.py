#!/usr/bin/env python3
"""
Reset Portfolio History

Wipes all portfolio data, holdings, and trade logs from the database
while preserving market data, cached news, and other configuration.

Usage: python scripts/reset_portfolio.py
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

def main():
    db_path = project_root / "data" / "agent.db"
    
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return 1

    print("⚠️  WARNING: PORTFOLIO RESET ⚠️")
    print("=" * 40)
    print("This will PERMANENTLY DELETE:")
    print("  - All portfolio snapshots")
    print("  - All historical holdings")
    print("  - All inferred trade logs")
    print("\nIt will NOT delete:")
    print("  - Cached market data")
    print("  - News analysis")
    print("  - AI recommendations")
    print("=" * 40)
    
    response = input("\nAre you sure you want to proceed? (type 'yes' to confirm): ")
    
    if response.lower() != 'yes':
        print("\n❌ Operation cancelled.")
        return 0
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Execute deletions
        cursor.execute("DELETE FROM trade_log")
        trades_deleted = cursor.rowcount
        
        cursor.execute("DELETE FROM holdings")
        holdings_deleted = cursor.rowcount
        
        cursor.execute("DELETE FROM portfolio_snapshot")
        snapshots_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print("\n✅ Portfolio history wiped successfully.")
        print(f"   - {snapshots_deleted} snapshots removed")
        print(f"   - {holdings_deleted} holdings records removed")
        print(f"   - {trades_deleted} trade logs removed")
        print("\nYou can now import a fresh portfolio CSV using scripts/import_portfolio.py")
        
    except Exception as e:
        print(f"\n❌ Error resetting database: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
