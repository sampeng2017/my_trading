"""
Unit Tests for Strategy Planner Agent
"""

import pytest
import sqlite3
import tempfile
import os
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.strategy_planner import StrategyPlanner

@pytest.fixture
def temp_db():
    """Create a temporary database with schema."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            price DECIMAL(10, 4),
            atr DECIMAL(10, 4),
            sma_50 DECIMAL(10, 4),
            volume INTEGER,
            is_volatile INTEGER DEFAULT 0,
            source TEXT
        );
        
        CREATE TABLE news_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            headline TEXT,
            sentiment TEXT,
            confidence DECIMAL(3, 2),
            implied_action TEXT,
            key_reason TEXT,
            urgency TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE strategy_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT,
            confidence DECIMAL(3, 2),
            reasoning TEXT,
            target_price DECIMAL(10, 4),
            stop_loss DECIMAL(10, 4),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_response TEXT,
            response_time DATETIME
        );
        
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
    """)
    
    # Seed data
    cursor.execute("""
        INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile)
        VALUES ('AAPL', 150.00, 3.00, 145.00, 0)
    """)
    
    cursor.execute("""
        INSERT INTO news_analysis (symbol, sentiment, confidence, implied_action)
        VALUES ('AAPL', 'positive', 0.9, 'BUY')
    """)
    
    # Create a portfolio snapshot to satisfy joins
    cursor.execute("INSERT INTO portfolio_snapshot (import_timestamp, total_equity, cash_balance) VALUES (?, 10000, 5000)", 
                  ('2025-01-01T00:00:00',))
    
    conn.commit()
    conn.close()
    
    yield db_path
    os.unlink(db_path)

@patch('agents.strategy_planner.GEMINI_AVAILABLE', True)
@patch('agents.strategy_planner.genai', create=True)
def test_generate_recommendation_buy(mock_genai, temp_db):
    """Test generating a BUY recommendation."""
    # Mock Gemini response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "action": "BUY",
        "confidence": 0.85,
        "reasoning": "Strong technicals and positive news sentiment.",
        "stop_loss": 145.00,
        "target_price": 160.00,
        "step1_technical_analysis": "Price above SMA50, uptrend.",
        "step2_sentiment_analysis": "Positive news flow.",
        "step3_risk_assessment": "Low volatility, good R/R."
    })
    
    mock_model.generate_content.return_value = mock_response
    mock_genai.GenerativeModel.return_value = mock_model
    
    planner = StrategyPlanner(temp_db, gemini_key="fake_key")
    
    rec = planner.generate_recommendation('AAPL')
    
    assert rec['symbol'] == 'AAPL'
    assert rec['action'] == 'BUY'
    assert rec['confidence'] == 0.85
    assert rec['stop_loss'] == 145.00

@patch('agents.strategy_planner.GEMINI_AVAILABLE', True)
@patch('agents.strategy_planner.genai', create=True)
def test_fallback_when_gemini_fails(mock_genai, temp_db):
    """Test fallback logic when AI fails."""
    # Mock Gemini exception
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("API Error")
    mock_genai.GenerativeModel.return_value = mock_model
    
    planner = StrategyPlanner(temp_db, gemini_key="fake_key")
    
    rec = planner.generate_recommendation('AAPL')
    
    # Should fall back to valid recommendation based on simpler logic or safe default
    assert rec['symbol'] == 'AAPL'
    assert rec['action'] in ['BUY', 'SELL', 'HOLD']
    assert rec['confidence'] < 1.0  # Fallback confidence is usually lower or 0

def test_missing_data_returns_none(temp_db):
    """Test that missing market data returns None."""
    planner = StrategyPlanner(temp_db)  # No Gemini key -> forced fallback
    
    rec = planner.generate_recommendation('UNKNOWN_SYMBOL')
    
    assert rec is None
