#!/usr/bin/env python3
"""
Import Portfolio CSV

Imports a Fidelity CSV export into the trading system database.
Usage: python scripts/import_portfolio.py [path/to/file.csv]

If no path provided, imports the most recent CSV from inbox/.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from agents.portfolio_accountant import PortfolioAccountant


def find_latest_csv(inbox_dir: Path) -> Path:
    """Find the most recently modified CSV in inbox."""
    csv_files = list(inbox_dir.glob("*.csv"))
    if not csv_files:
        return None
    return max(csv_files, key=lambda f: f.stat().st_mtime)


def main():
    db_path = project_root / "data" / "agent.db"
    inbox_dir = project_root / "inbox"

    # Check database exists
    if not db_path.exists():
        print("❌ Database not found. Initialize first:")
        print("   sqlite3 data/agent.db < data/init_schema.sql")
        return 1

    # Determine CSV file to import
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        if not csv_path.is_absolute():
            csv_path = project_root / csv_path
    else:
        csv_path = find_latest_csv(inbox_dir)
        if not csv_path:
            print("❌ No CSV files found in inbox/")
            print("   Drop a Fidelity CSV export into the inbox/ folder")
            print("   Or specify a path: python scripts/import_portfolio.py path/to/file.csv")
            return 1
        print(f"📄 Using most recent CSV: {csv_path.name}")

    if not csv_path.exists():
        print(f"❌ File not found: {csv_path}")
        return 1

    # Import the CSV
    print(f"\n📥 Importing: {csv_path}")
    print("-" * 50)

    try:
        pa = PortfolioAccountant(str(db_path))
        snapshot_id = pa.import_fidelity_csv(str(csv_path))

        if snapshot_id:
            snapshot = pa.get_latest_snapshot()

            print(f"\n✅ Import successful! Snapshot #{snapshot_id}")
            print(f"\n{'='*50}")
            print(f"{'PORTFOLIO SUMMARY':^50}")
            print(f"{'='*50}")
            print(f"  Total Equity:  ${snapshot['total_equity']:>15,.2f}")
            print(f"  Cash Balance:  ${snapshot['cash_balance']:>15,.2f}")
            print(f"  Invested:      ${snapshot['total_equity'] - snapshot['cash_balance']:>15,.2f}")
            print(f"  Positions:     {len(snapshot['holdings']):>15}")

            if snapshot['holdings']:
                print(f"\n{'HOLDINGS':^50}")
                print("-" * 50)
                print(f"  {'Symbol':<8} {'Shares':>10} {'Cost Basis':>12} {'Value':>12}")
                print("-" * 50)
                for h in snapshot['holdings']:
                    print(f"  {h['symbol']:<8} {h['quantity']:>10,.2f} ${h['cost_basis']:>10,.2f} ${h['current_value']:>10,.2f}")

            print(f"\n{'='*50}")
        else:
            print("❌ Import failed - no snapshot created")
            return 1

    except Exception as e:
        print(f"❌ Import error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
