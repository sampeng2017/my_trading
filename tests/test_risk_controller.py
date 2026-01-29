"""
Unit Tests for Risk Controller Agent
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.risk_controller import RiskController


@pytest.fixture
def temp_db():
    """Create a temporary database with schema."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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
            current_value DECIMAL(15, 2)
        );
        
        CREATE TABLE market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            price DECIMAL(10, 4),
            atr DECIMAL(10, 4),
            sma_50 DECIMAL(10, 4),
            is_volatile INTEGER DEFAULT 0,
            source TEXT
        );
        
        CREATE TABLE stock_metadata (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            industry TEXT,
            avg_volume_20d INTEGER,
            last_updated DATETIME
        );
        
        CREATE TABLE risk_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT,
            approved INTEGER,
            reason TEXT,
            approved_shares INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    os.unlink(db_path)


@pytest.fixture
def setup_portfolio(temp_db):
    """Set up a standard portfolio state for testing."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    # Create portfolio snapshot: $10,000 equity, $5,000 cash
    cursor.execute("""
        INSERT INTO portfolio_snapshot (import_timestamp, total_equity, cash_balance)
        VALUES (datetime('now'), 10000.00, 5000.00)
    """)
    snapshot_id = cursor.lastrowid
    
    # Add existing holding: AAPL - $3,000 value
    cursor.execute("""
        INSERT INTO holdings (snapshot_id, symbol, quantity, cost_basis, current_value)
        VALUES (?, 'AAPL', 20, 150.00, 3000.00)
    """, (snapshot_id,))
    
    # Add MSFT - $2,000 value
    cursor.execute("""
        INSERT INTO holdings (snapshot_id, symbol, quantity, cost_basis, current_value)
        VALUES (?, 'MSFT', 5, 400.00, 2000.00)
    """, (snapshot_id,))
    
    # Add market data
    cursor.execute("""
        INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile)
        VALUES ('AAPL', 150.00, 3.00, 145.00, 0)
    """)
    cursor.execute("""
        INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile)
        VALUES ('MSFT', 400.00, 8.00, 390.00, 0)
    """)
    cursor.execute("""
        INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile)
        VALUES ('TSLA', 200.00, 5.00, 190.00, 0)
    """)
    cursor.execute("""
        INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile)
        VALUES ('HIGH_VOL', 100.00, 15.00, 95.00, 1)
    """)
    
    # Add sector metadata
    cursor.execute("""
        INSERT INTO stock_metadata (symbol, sector) VALUES ('AAPL', 'Technology')
    """)
    cursor.execute("""
        INSERT INTO stock_metadata (symbol, sector) VALUES ('MSFT', 'Technology')
    """)
    cursor.execute("""
        INSERT INTO stock_metadata (symbol, sector) VALUES ('TSLA', 'Automotive')
    """)
    
    conn.commit()
    conn.close()
    
    return temp_db


class TestRiskControllerBasics:
    """Basic Risk Controller tests."""
    
    def test_init(self, temp_db):
        """Test controller initialization."""
        controller = RiskController(temp_db)
        assert controller.MAX_POSITION_SIZE_PCT == 0.20
        assert controller.RISK_PER_TRADE_PCT == 0.015
    
    def test_hold_always_approved(self, setup_portfolio):
        """Test that HOLD actions are always approved."""
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'AAPL',
            'action': 'HOLD',
            'confidence': 0.5
        })
        
        assert result['approved'] is True
        assert result['reason'] == 'No action required'


class TestBuyValidation:
    """Test BUY trade validation."""
    
    def test_buy_approved_new_position(self, setup_portfolio):
        """Test BUY for a new position passes all checks."""
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'TSLA',
            'action': 'BUY',
            'confidence': 0.8
        })
        
        assert result['approved'] is True
        assert 'approved_shares' in result
        assert result['approved_shares'] > 0
    
    def test_buy_rejected_insufficient_cash(self, setup_portfolio):
        """Test BUY rejected when insufficient cash."""
        # Modify to have only $10 cash
        conn = sqlite3.connect(setup_portfolio)
        conn.execute("UPDATE portfolio_snapshot SET cash_balance = 10.00")
        conn.commit()
        conn.close()
        
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'TSLA',
            'action': 'BUY',
            'confidence': 0.8
        })
        
        assert result['approved'] is False
        assert 'Insufficient cash' in result['reason'] or 'less than 1 share' in result['reason']
    
    def test_buy_rejected_position_size_limit(self, setup_portfolio):
        """Test BUY rejected when position would exceed 20% limit."""
        # AAPL already at $3,000 (30% of $10k)
        # Try to add more - should be limited or rejected
        controller = RiskController(setup_portfolio)
        
        # Force a large position request
        conn = sqlite3.connect(setup_portfolio)
        conn.execute("UPDATE market_data SET price = 50.00, atr = 1.00 WHERE symbol = 'AAPL'")
        conn.commit()
        conn.close()
        
        result = controller.validate_trade({
            'symbol': 'AAPL',
            'action': 'BUY',
            'confidence': 0.9
        })
        
        # Should either be rejected or reduced
        if result['approved']:
            # Position should be capped
            total_value = 3000 + result.get('approved_cost', 0)
            assert total_value <= 10000 * 0.20 + 100  # Allow small margin
    
    def test_buy_rejected_excessive_volatility(self, setup_portfolio):
        """Test BUY rejected for high volatility stock."""
        controller = RiskController(setup_portfolio)
        
        # HIGH_VOL has ATR of $15 on $100 price = 15% > 10% limit
        result = controller.validate_trade({
            'symbol': 'HIGH_VOL',
            'action': 'BUY',
            'confidence': 0.8
        })
        
        assert result['approved'] is False
        assert 'volatility' in result['reason'].lower()
    
    def test_buy_stop_loss_calculated(self, setup_portfolio):
        """Test that stop loss is calculated."""
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'TSLA',
            'action': 'BUY',
            'confidence': 0.8
        })
        
        if result['approved']:
            assert 'calculated_stop_loss' in result
            # Stop should be below price ($200)
            assert result['calculated_stop_loss'] < 200


class TestSellValidation:
    """Test SELL trade validation."""
    
    def test_sell_approved_existing_position(self, setup_portfolio):
        """Test SELL approved for existing position."""
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'AAPL',
            'action': 'SELL',
            'confidence': 0.7
        })
        
        assert result['approved'] is True
        assert result['approved_shares'] == 20  # Full position
    
    def test_sell_rejected_no_position(self, setup_portfolio):
        """Test SELL rejected when no position held."""
        controller = RiskController(setup_portfolio)
        
        result = controller.validate_trade({
            'symbol': 'GOOGL',  # Not in portfolio
            'action': 'SELL',
            'confidence': 0.7
        })
        
        assert result['approved'] is False
        assert 'No position' in result['reason']


class TestPositionSizing:
    """Test position sizing calculations."""
    
    def test_calculate_position_size(self, setup_portfolio):
        """Test position size calculation."""
        controller = RiskController(setup_portfolio)
        
        result = controller.calculate_position_size('TSLA', 200.00)
        
        assert 'shares' in result
        assert 'cost' in result
        assert 'stop_loss' in result
        assert result['shares'] > 0
        assert result['stop_loss'] < 200.00
    
    def test_position_size_respects_cash(self, setup_portfolio):
        """Test position size doesn't exceed cash."""
        controller = RiskController(setup_portfolio)
        
        result = controller.calculate_position_size('TSLA', 200.00)
        
        assert result['cost'] <= 5000.00  # Cash balance


class TestRiskSummary:
    """Test risk summary reporting."""
    
    def test_get_risk_summary(self, setup_portfolio):
        """Test risk summary generation."""
        controller = RiskController(setup_portfolio)
        
        summary = controller.get_risk_summary()
        
        assert summary['total_equity'] == 10000.00
        assert summary['cash_balance'] == 5000.00
        assert summary['num_positions'] == 2
        assert 'largest_position' in summary


class TestConfigOverrides:
    """Test configuration overrides."""
    
    def test_custom_config(self, temp_db):
        """Test custom risk parameters."""
        config = {
            'risk': {
                'max_position_size_pct': 0.10,  # 10% instead of 20%
                'risk_per_trade_pct': 0.01  # 1% instead of 1.5%
            }
        }
        
        controller = RiskController(temp_db, config=config)
        
        assert controller.MAX_POSITION_SIZE_PCT == 0.10
        assert controller.RISK_PER_TRADE_PCT == 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
