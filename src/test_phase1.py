#!/usr/bin/env python3
"""
Phase 1 Integration Test

Tests the foundational components:
1. Database initialization
2. CSV import via Portfolio Accountant
3. Price fetching via Market Analyst
4. Display portfolio with current values
"""

import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

import sqlite3
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database(db_path: str):
    """Initialize database with schema."""
    schema_path = project_root / 'data' / 'init_schema.sql'
    
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    with open(schema_path, 'r') as f:
        schema = f.read()
    
    cursor.executescript(schema)
    conn.commit()
    conn.close()
    
    logger.info(f"Database initialized at {db_path}")
    return True


def test_portfolio_import(db_path: str):
    """Test CSV import."""
    from agents.portfolio_accountant import PortfolioAccountant
    
    # Find sample CSV
    sample_csv = project_root / 'inbox' / 'sample_portfolio.csv'
    
    if not sample_csv.exists():
        logger.error(f"Sample CSV not found: {sample_csv}")
        return None
    
    accountant = PortfolioAccountant(db_path)
    snapshot_id = accountant.import_fidelity_csv(str(sample_csv))
    
    logger.info(f"Portfolio imported, snapshot ID: {snapshot_id}")
    
    return accountant.get_latest_snapshot()


def test_market_data(db_path: str, symbols: list):
    """Test market data fetching."""
    from agents.market_analyst import MarketAnalyst
    
    # Initialize without API keys (will use yfinance)
    analyst = MarketAnalyst(db_path)
    
    logger.info(f"Fetching market data for: {symbols}")
    results = analyst.scan_symbols(symbols)
    
    return results


def display_portfolio(snapshot: dict, market_data: dict):
    """Display portfolio summary."""
    print("\n" + "=" * 60)
    print("         PORTFOLIO SNAPSHOT")
    print("=" * 60)
    print()
    
    # Header
    print(f"{'Symbol':<8} {'Shares':>8} {'Price':>12} {'Value':>14} {'Change':>10}")
    print("-" * 60)
    
    total_value = 0
    
    for holding in snapshot.get('holdings', []):
        symbol = holding['symbol']
        quantity = holding['quantity']
        csv_value = holding['current_value']
        
        # Get live price if available
        if symbol in market_data:
            live_price = market_data[symbol].get('price', 0)
            live_value = quantity * live_price
            change = live_value - csv_value
            change_str = f"{'+'if change >= 0 else ''}{change:,.2f}"
        else:
            live_price = csv_value / quantity if quantity > 0 else 0
            live_value = csv_value
            change_str = "N/A"
        
        print(f"{symbol:<8} {quantity:>8.0f} ${live_price:>10,.2f} ${live_value:>12,.2f} {change_str:>10}")
        total_value += live_value
    
    print("-" * 60)
    
    cash = snapshot.get('cash_balance', 0)
    print(f"{'Cash':<8} {'':<8} {'':<12} ${cash:>12,.2f}")
    
    total_equity = total_value + cash
    
    print("=" * 60)
    print(f"{'TOTAL EQUITY':<30} ${total_equity:>26,.2f}")
    print("=" * 60)
    
    # Show market status
    print("\nMarket Data Status:")
    for symbol in [h['symbol'] for h in snapshot.get('holdings', [])]:
        if symbol in market_data:
            data = market_data[symbol]
            volatility = "⚠️ HIGH" if data.get('is_volatile') else "Normal"
            source = data.get('source', 'Unknown')
            print(f"  {symbol}: ${data['price']:,.2f} | ATR: ${data.get('atr', 0):,.2f} | Volatility: {volatility} | Source: {source}")
        else:
            print(f"  {symbol}: No data available")


def main():
    """Run Phase 1 integration test."""
    print("\n" + "=" * 60)
    print("    PHASE 1 INTEGRATION TEST")
    print("    Automated Stock Trading System")
    print("=" * 60 + "\n")
    
    # Setup paths
    db_path = project_root / 'data' / 'agent.db'
    
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Initialize database
    print("Step 1: Initializing database...")
    if not init_database(str(db_path)):
        print("❌ Database initialization failed")
        return 1
    print("✅ Database initialized\n")
    
    # Step 2: Import portfolio
    print("Step 2: Importing portfolio CSV...")
    snapshot = test_portfolio_import(str(db_path))
    if not snapshot:
        print("❌ Portfolio import failed")
        return 1
    print(f"✅ Portfolio imported ({len(snapshot.get('holdings', []))} holdings)\n")
    
    # Step 3: Fetch market data
    print("Step 3: Fetching live market data...")
    symbols = [h['symbol'] for h in snapshot.get('holdings', [])]
    market_data = test_market_data(str(db_path), symbols)
    print(f"✅ Market data fetched for {len(market_data)} symbols\n")
    
    # Step 4: Display results
    print("Step 4: Portfolio Summary")
    display_portfolio(snapshot, market_data)
    
    print("\n✅ Phase 1 Integration Test Completed Successfully!")
    print(f"\nDatabase location: {db_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
