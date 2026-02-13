"""
Unit Tests for Recommendation Evaluator Agent
"""

import pytest
import sqlite3
import tempfile
import os
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Force local SQLite for tests (must be before importing agents)
os.environ['DB_MODE'] = 'local'

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.recommendation_evaluator import RecommendationEvaluator


@pytest.fixture
def temp_db():
    """Create a temporary database with schema."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
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

        CREATE TABLE recommendation_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            original_action TEXT NOT NULL,
            original_confidence DECIMAL(3, 2),
            original_target_price DECIMAL(10, 4),
            original_stop_loss DECIMAL(10, 4),
            recommendation_date DATETIME NOT NULL,
            evaluation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            price_at_recommendation DECIMAL(10, 4),
            price_at_evaluation DECIMAL(10, 4),
            price_change_pct DECIMAL(8, 4),
            target_hit INTEGER DEFAULT 0,
            stop_loss_hit INTEGER DEFAULT 0,
            max_favorable_move_pct DECIMAL(8, 4),
            max_adverse_move_pct DECIMAL(8, 4),
            score TEXT CHECK(score IN ('excellent', 'good', 'neutral', 'poor', 'bad')),
            ai_assessment TEXT,
            FOREIGN KEY(recommendation_id) REFERENCES strategy_recommendations(id)
        );
    """)

    conn.commit()
    conn.close()

    yield db_path
    os.unlink(db_path)


def _insert_recommendation(db_path, symbol, action, confidence, target_price=None,
                            stop_loss=None, days_ago=10, reasoning="Test reasoning"):
    """Helper to insert a recommendation N days ago."""
    timestamp = (datetime.now() - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO strategy_recommendations
        (symbol, action, confidence, reasoning, target_price, stop_loss, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (symbol, action, confidence, reasoning, target_price, stop_loss, timestamp))
    conn.commit()
    rec_id = cursor.lastrowid
    conn.close()
    return rec_id


def _make_price_history(start_price, end_price, days=10, high_factor=1.02, low_factor=0.98):
    """Generate synthetic price history for testing."""
    prices = []
    step = (end_price - start_price) / max(days - 1, 1)
    for i in range(days):
        close = start_price + step * i
        prices.append({
            'date': (datetime.now() - timedelta(days=days - i)).strftime('%Y-%m-%d'),
            'open': close * 0.999,
            'high': close * high_factor,
            'low': close * low_factor,
            'close': close,
            'volume': 1000000
        })
    return prices


class TestScoring:
    """Test deterministic scoring logic."""

    def test_score_buy_excellent_target_hit(self, temp_db):
        """BUY rec where target was hit should score 'excellent'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'BUY', 'target_price': 160.0, 'stop_loss': 140.0}
        metrics = {
            'price_change_pct': 8.0,
            'target_hit': 1,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'excellent'

    def test_score_buy_good(self, temp_db):
        """BUY rec with >5% gain, no target hit should score 'good'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'BUY', 'target_price': 200.0, 'stop_loss': 140.0}
        metrics = {
            'price_change_pct': 6.5,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'good'

    def test_score_buy_neutral(self, temp_db):
        """BUY rec with small price movement should score 'neutral'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'BUY', 'target_price': 160.0, 'stop_loss': 140.0}
        metrics = {
            'price_change_pct': 1.5,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'neutral'

    def test_score_buy_poor(self, temp_db):
        """BUY rec with moderate decline should score 'poor'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'BUY', 'target_price': 160.0, 'stop_loss': 140.0}
        metrics = {
            'price_change_pct': -3.5,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'poor'

    def test_score_buy_bad_stop_hit(self, temp_db):
        """BUY rec where stop loss was hit should score 'bad'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'BUY', 'target_price': 160.0, 'stop_loss': 140.0}
        metrics = {
            'price_change_pct': -7.0,
            'target_hit': 0,
            'stop_loss_hit': 1
        }
        assert evaluator._score_recommendation(rec, metrics) == 'bad'

    def test_score_sell_excellent(self, temp_db):
        """SELL rec where target was hit should score 'excellent'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'SELL', 'target_price': 90.0, 'stop_loss': 110.0}
        metrics = {
            'price_change_pct': -8.0,
            'target_hit': 1,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'excellent'

    def test_score_sell_good(self, temp_db):
        """SELL rec with >5% decline but no target hit should score 'good'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'SELL'}
        metrics = {
            'price_change_pct': -8.0,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'good'

    def test_score_sell_bad(self, temp_db):
        """SELL rec where price rose significantly should score 'bad'."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'action': 'SELL'}
        metrics = {
            'price_change_pct': 7.0,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        assert evaluator._score_recommendation(rec, metrics) == 'bad'


class TestMetrics:
    """Test metrics calculation."""

    def test_metrics_basic_buy_gain(self, temp_db):
        """Test basic price change calculation for a BUY that gained."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {
            'action': 'BUY',
            'target_price': 115.0,
            'stop_loss': 90.0,
            'timestamp': (datetime.now() - timedelta(days=10)).isoformat()
        }
        prices = _make_price_history(100.0, 110.0, days=10)

        metrics = evaluator._calculate_metrics(rec, prices)

        assert metrics is not None
        assert metrics['price_at_recommendation'] == 99.9
        assert metrics['price_at_evaluation'] == 110.0
        assert abs(metrics['price_change_pct'] - 10.0) < 0.5
        assert metrics['max_favorable_move_pct'] > 0

    def test_metrics_buy_target_hit(self, temp_db):
        """Test that target_hit is detected when high exceeds target."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {
            'action': 'BUY',
            'target_price': 105.0,
            'stop_loss': 90.0,
            'timestamp': (datetime.now() - timedelta(days=10)).isoformat()
        }
        # Price goes from 100 to 110, with highs 2% above close
        prices = _make_price_history(100.0, 110.0, days=10, high_factor=1.02)

        metrics = evaluator._calculate_metrics(rec, prices)

        assert metrics['target_hit'] == 1

    def test_metrics_buy_stop_hit(self, temp_db):
        """Test that stop_loss_hit is detected when low breaches stop."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {
            'action': 'BUY',
            'target_price': 120.0,
            'stop_loss': 96.0,
            'timestamp': (datetime.now() - timedelta(days=9)).isoformat()
        }
        # Price drops from 100 to 90, lows are 2% below close
        prices = _make_price_history(100.0, 90.0, days=10, low_factor=0.97)

        metrics = evaluator._calculate_metrics(rec, prices)

        assert metrics['stop_loss_hit'] == 1

    def test_metrics_empty_prices(self, temp_db):
        """Test that empty price list returns None."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {
            'action': 'BUY',
            'target_price': 110.0,
            'stop_loss': 90.0,
            'timestamp': datetime.now().isoformat()
        }

        metrics = evaluator._calculate_metrics(rec, [])
        assert metrics is None


class TestEligibility:
    """Test eligible recommendation querying."""

    def test_no_eligible_recommendations(self, temp_db):
        """Empty DB should return no eligible recs."""
        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert eligible == []

    def test_recent_recommendations_excluded(self, temp_db):
        """Recommendations newer than min_age_days should be excluded."""
        _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.8, days_ago=3)
        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert len(eligible) == 0

    def test_old_recommendations_excluded(self, temp_db):
        """Recommendations older than max_age_days should be excluded."""
        _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.8, days_ago=30)
        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert len(eligible) == 0

    def test_eligible_recommendation_found(self, temp_db):
        """Recommendations in the window should be found."""
        _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.8, days_ago=10)
        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert len(eligible) == 1
        assert eligible[0]['symbol'] == 'AAPL'

    def test_hold_recommendations_excluded(self, temp_db):
        """HOLD recommendations should not be eligible for evaluation."""
        _insert_recommendation(temp_db, 'AAPL', 'HOLD', 0.5, days_ago=10)
        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert len(eligible) == 0

    def test_already_evaluated_skipped(self, temp_db):
        """Previously evaluated recommendations should not be re-evaluated."""
        rec_id = _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.8, days_ago=10)

        # Mark it as already evaluated
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        rec_date = (datetime.now() - timedelta(days=10)).isoformat()
        cursor.execute("""
            INSERT INTO recommendation_evaluations
            (recommendation_id, symbol, original_action, recommendation_date, score)
            VALUES (?, 'AAPL', 'BUY', ?, 'good')
        """, (rec_id, rec_date))
        conn.commit()
        conn.close()

        evaluator = RecommendationEvaluator(temp_db)
        eligible = evaluator._get_eligible_recommendations(10, 7, 21)
        assert len(eligible) == 0


class TestEvaluation:
    """Test full evaluation flow."""

    @patch('agents.recommendation_evaluator.YFINANCE_AVAILABLE', True)
    @patch('agents.recommendation_evaluator.yf')
    def test_evaluate_single_buy_success(self, mock_yf, temp_db):
        """Test evaluating a successful BUY recommendation."""
        rec_id = _insert_recommendation(
            temp_db, 'AAPL', 'BUY', 0.85,
            target_price=160.0, stop_loss=140.0, days_ago=10
        )

        # Mock yfinance to return price history showing a gain
        mock_ticker = MagicMock()
        import pandas as pd
        dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
        mock_df = pd.DataFrame({
            'Open': [139 + i for i in range(20)],
            'High': [141 + i for i in range(20)],
            'Low': [137 + i for i in range(20)],
            'Close': [140 + i for i in range(20)],
            'Volume': [1000000] * 20
        }, index=dates)
        mock_ticker.history.return_value = mock_df
        mock_yf.Ticker.return_value = mock_ticker

        evaluator = RecommendationEvaluator(temp_db)
        result = evaluator.evaluate_recommendations(top_n=10, min_age_days=7, max_age_days=21)

        assert result['total_evaluated'] == 1
        assert len(result['evaluations']) == 1
        eval_result = result['evaluations'][0]
        assert eval_result['symbol'] == 'AAPL'
        assert eval_result['original_action'] == 'BUY'
        assert eval_result['score'] in ('excellent', 'good', 'neutral', 'poor', 'bad')

    @patch('agents.recommendation_evaluator.YFINANCE_AVAILABLE', False)
    def test_evaluate_without_yfinance(self, temp_db):
        """Without yfinance, evaluation should return error."""
        _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.85, days_ago=10)

        evaluator = RecommendationEvaluator(temp_db)
        result = evaluator.evaluate_recommendations()

        assert 'error' in result

    def test_evaluate_no_eligible(self, temp_db):
        """No eligible recs should return empty results."""
        evaluator = RecommendationEvaluator(temp_db)
        result = evaluator.evaluate_recommendations()

        assert result['total_evaluated'] == 0
        assert result['evaluations'] == []


class TestGetRecentEvaluations:
    """Test reading evaluations from DB."""

    def test_empty_table(self, temp_db):
        """Empty evaluations table should return empty list."""
        evaluator = RecommendationEvaluator(temp_db)
        results = evaluator.get_recent_evaluations()
        assert results == []

    def test_read_stored_evaluation(self, temp_db):
        """Should read back a stored evaluation."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recommendation_evaluations
            (recommendation_id, symbol, original_action, original_confidence,
             recommendation_date, price_at_recommendation, price_at_evaluation,
             price_change_pct, target_hit, stop_loss_hit,
             max_favorable_move_pct, max_adverse_move_pct, score, ai_assessment)
            VALUES (1, 'AAPL', 'BUY', 0.85, '2026-01-20', 150.0, 160.0,
                    6.67, 1, 0, 8.5, -1.2, 'good', 'Strong buy delivered returns.')
        """)
        conn.commit()
        conn.close()

        evaluator = RecommendationEvaluator(temp_db)
        results = evaluator.get_recent_evaluations()

        assert len(results) == 1
        assert results[0]['symbol'] == 'AAPL'
        assert results[0]['score'] == 'good'
        assert results[0]['price_change_pct'] == 6.67

    def test_filter_by_symbol(self, temp_db):
        """Should filter evaluations by symbol."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        rec_date = '2026-01-20'
        cursor.execute("""
            INSERT INTO recommendation_evaluations
            (recommendation_id, symbol, original_action, recommendation_date, score)
            VALUES (1, 'AAPL', 'BUY', ?, 'good'), (2, 'GOOGL', 'BUY', ?, 'neutral')
        """, (rec_date, rec_date))
        conn.commit()
        conn.close()

        evaluator = RecommendationEvaluator(temp_db)
        results = evaluator.get_recent_evaluations(symbol='AAPL')

        assert len(results) == 1
        assert results[0]['symbol'] == 'AAPL'


class TestFallbackAssessment:
    """Test rule-based fallback assessments."""

    def test_buy_good_fallback(self, temp_db):
        """Good BUY should generate positive fallback text."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'symbol': 'AAPL', 'action': 'BUY'}
        metrics = {
            'price_change_pct': 7.0,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        text = evaluator._fallback_assessment(rec, metrics, 'good')
        assert 'AAPL' in text
        assert 'good' in text

    def test_buy_bad_fallback(self, temp_db):
        """Bad BUY should generate negative fallback text."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'symbol': 'TSLA', 'action': 'BUY'}
        metrics = {
            'price_change_pct': -8.0,
            'target_hit': 0,
            'stop_loss_hit': 1
        }
        text = evaluator._fallback_assessment(rec, metrics, 'bad')
        assert 'TSLA' in text
        assert 'bad' in text
        assert 'stop loss' in text.lower()

    def test_sell_good_fallback(self, temp_db):
        """Good SELL should generate positive fallback text."""
        evaluator = RecommendationEvaluator(temp_db)
        rec = {'symbol': 'META', 'action': 'SELL'}
        metrics = {
            'price_change_pct': -5.0,
            'target_hit': 0,
            'stop_loss_hit': 0
        }
        text = evaluator._fallback_assessment(rec, metrics, 'good')
        assert 'META' in text
        assert 'good' in text


class TestParameterOverrides:
    """Test that parameter overrides work correctly, including zero values."""

    def test_zero_top_n_not_swallowed(self, temp_db):
        """Passing top_n=0 should use 0, not fall back to config default."""
        evaluator = RecommendationEvaluator(temp_db)
        _insert_recommendation(temp_db, 'AAPL', 'BUY', 0.8, days_ago=10)
        result = evaluator.evaluate_recommendations(top_n=0)
        assert result['total_evaluated'] == 0
        assert result['evaluations'] == []

