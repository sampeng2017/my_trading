"""
Unit Tests for Portfolio Accountant Agent
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.portfolio_accountant import PortfolioAccountant


@pytest.fixture
def temp_db():
    """Create a temporary database with schema."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Initialize schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create necessary tables
    cursor.executescript("""
        CREATE TABLE portfolio_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_timestamp DATETIME NOT NULL,
            total_equity DECIMAL(15, 2),
            cash_balance DECIMAL(15, 2)
        );
        
        CREATE TABLE holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity DECIMAL(10, 4),
            cost_basis DECIMAL(10, 4),
            current_value DECIMAL(15, 2),
            FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshot(id)
        );
        
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT CHECK(action IN ('BUY', 'SELL')),
            quantity DECIMAL(10, 4),
            snapshot_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshot(id)
        );
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample Fidelity CSV file."""
    csv_content = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,AAPL,APPLE INC,50,178.45,8922.50,8500.00,170.00,422.50,4.97,Cash
Z12345678,Individual,MSFT,MICROSOFT CORP,20,380.20,7604.00,7200.00,360.00,404.00,5.61,Cash
Z12345678,Individual,SPAXX,FIDELITY GOVERNMENT MONEY MARKET,3500.00,1.00,3500.00,3500.00,1.00,0.00,0.00,Cash
"""
    csv_path = tmp_path / "fidelity_export.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)


@pytest.fixture
def sample_csv_v2(tmp_path):
    """Create a second CSV for state diffing test."""
    csv_content = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,AAPL,APPLE INC,60,180.00,10800.00,10200.00,170.00,600.00,5.88,Cash
Z12345678,Individual,MSFT,MICROSOFT CORP,10,385.00,3850.00,3600.00,360.00,250.00,6.94,Cash
Z12345678,Individual,TSLA,TESLA INC,15,200.00,3000.00,2850.00,190.00,150.00,5.26,Cash
Z12345678,Individual,SPAXX,FIDELITY GOVERNMENT MONEY MARKET,2500.00,1.00,2500.00,2500.00,1.00,0.00,0.00,Cash
"""
    csv_path = tmp_path / "fidelity_export_v2.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)


class TestPortfolioAccountant:
    """Test cases for Portfolio Accountant."""
    
    def test_init(self, temp_db):
        """Test agent initialization."""
        accountant = PortfolioAccountant(temp_db)
        assert accountant.db_path == temp_db
    
    def test_import_csv(self, temp_db, sample_csv):
        """Test CSV import creates correct snapshot."""
        accountant = PortfolioAccountant(temp_db)
        snapshot_id = accountant.import_fidelity_csv(sample_csv)
        
        assert snapshot_id is not None
        assert snapshot_id > 0
        
        # Verify snapshot was created
        snapshot = accountant.get_latest_snapshot()
        assert snapshot is not None
        assert snapshot['id'] == snapshot_id
    
    def test_portfolio_totals(self, temp_db, sample_csv):
        """Test that portfolio totals are calculated correctly."""
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(sample_csv)
        
        snapshot = accountant.get_latest_snapshot()
        
        # Expected: AAPL ($8922.50) + MSFT ($7604.00) + Cash ($3500.00) = $20,026.50
        expected_equity = 8922.50 + 7604.00 + 3500.00
        
        assert snapshot['total_equity'] == pytest.approx(expected_equity, rel=0.01)
        assert snapshot['cash_balance'] == pytest.approx(3500.00, rel=0.01)
    
    def test_holdings_extraction(self, temp_db, sample_csv):
        """Test that holdings are extracted correctly."""
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(sample_csv)
        
        snapshot = accountant.get_latest_snapshot()
        holdings = snapshot['holdings']
        
        # Should have 2 holdings (AAPL and MSFT, not SPAXX which is cash)
        assert len(holdings) == 2
        
        symbols = [h['symbol'] for h in holdings]
        assert 'AAPL' in symbols
        assert 'MSFT' in symbols
        assert 'SPAXX' not in symbols
    
    def test_holding_details(self, temp_db, sample_csv):
        """Test that holding details are correct."""
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(sample_csv)
        
        snapshot = accountant.get_latest_snapshot()
        
        # Find AAPL holding
        aapl = next((h for h in snapshot['holdings'] if h['symbol'] == 'AAPL'), None)
        
        assert aapl is not None
        assert aapl['quantity'] == 50
        assert aapl['cost_basis'] == pytest.approx(170.00, rel=0.01)
        assert aapl['current_value'] == pytest.approx(8922.50, rel=0.01)
    
    def test_cash_detection(self, temp_db, sample_csv):
        """Test that cash (SPAXX) is detected as cash, not holding."""
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(sample_csv)
        
        snapshot = accountant.get_latest_snapshot()
        
        # SPAXX should be in cash_balance, not in holdings
        assert snapshot['cash_balance'] == pytest.approx(3500.00, rel=0.01)
        
        spaxx = next((h for h in snapshot['holdings'] if h['symbol'] == 'SPAXX'), None)
        assert spaxx is None
    
    def test_get_holdings_symbols(self, temp_db, sample_csv):
        """Test getting list of held symbols."""
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(sample_csv)
        
        symbols = accountant.get_holdings_symbols()
        
        assert sorted(symbols) == ['AAPL', 'MSFT']
    
    def test_state_diffing(self, temp_db, sample_csv, sample_csv_v2):
        """Test that trades are inferred from state changes."""
        accountant = PortfolioAccountant(temp_db)
        
        # Import first snapshot
        accountant.import_fidelity_csv(sample_csv)
        
        # Import second snapshot
        accountant.import_fidelity_csv(sample_csv_v2)
        
        # Check trade log for inferred trades
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT symbol, action, quantity FROM trade_log ORDER BY symbol")
        trades = cursor.fetchall()
        conn.close()
        
        # Expected trades:
        # AAPL: 50 -> 60 = BUY 10
        # MSFT: 20 -> 10 = SELL 10
        # TSLA: 0 -> 15 = BUY 15
        
        trade_dict = {t[0]: (t[1], t[2]) for t in trades}
        
        assert 'AAPL' in trade_dict
        assert trade_dict['AAPL'] == ('BUY', 10)
        
        assert 'MSFT' in trade_dict
        assert trade_dict['MSFT'] == ('SELL', 10)
        
        assert 'TSLA' in trade_dict
        assert trade_dict['TSLA'] == ('BUY', 15)
    
    def test_empty_portfolio(self, temp_db, tmp_path):
        """Test handling of empty portfolio."""
        csv_content = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,SPAXX,FIDELITY GOVERNMENT MONEY MARKET,10000.00,1.00,10000.00,10000.00,1.00,0.00,0.00,Cash
"""
        csv_path = tmp_path / "empty_portfolio.csv"
        csv_path.write_text(csv_content)
        
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(str(csv_path))
        
        snapshot = accountant.get_latest_snapshot()
        
        assert snapshot['total_equity'] == pytest.approx(10000.00, rel=0.01)
        assert snapshot['cash_balance'] == pytest.approx(10000.00, rel=0.01)
        assert len(snapshot['holdings']) == 0


class TestCurrencyParsing:
    """Test currency parsing edge cases."""
    
    def test_parse_with_dollar_sign(self, temp_db, tmp_path):
        """Test parsing values with $ sign."""
        csv_content = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,AAPL,APPLE INC,50,$178.45,"$8,922.50","$8,500.00",$170.00,$422.50,4.97%,Cash
"""
        csv_path = tmp_path / "dollar_format.csv"
        csv_path.write_text(csv_content)
        
        accountant = PortfolioAccountant(temp_db)
        accountant.import_fidelity_csv(str(csv_path))
        
        snapshot = accountant.get_latest_snapshot()
        aapl = snapshot['holdings'][0]
        
        assert aapl['current_value'] == pytest.approx(8922.50, rel=0.01)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
