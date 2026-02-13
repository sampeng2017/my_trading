"""
Recommendation Evaluator Agent

Evaluates past trade recommendations against actual market performance.
Handles:
- Fetching eligible past recommendations from database
- Retrieving actual price history via yfinance
- Computing objective performance metrics (price change, target/stop hits)
- Deterministic scoring of each recommendation
- AI-generated narrative assessments via Gemini
- Summary report generation
"""

from src.data.db_connection import get_connection
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging
import time

from src.utils.gemini_client import call_with_retry

logger = logging.getLogger(__name__)

# Try to import Google Generative AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. AI assessments will be unavailable.")

# Try yfinance for historical prices
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Evaluation requires yfinance for price history.")


class RecommendationEvaluator:
    """Agent responsible for evaluating past recommendation quality."""

    def __init__(self, db_path: str, gemini_key: Optional[str] = None,
                 config: Optional[Dict] = None):
        """
        Initialize Recommendation Evaluator.

        Args:
            db_path: Path to SQLite database
            gemini_key: Google Gemini API key (optional, for AI narratives)
            config: Configuration dict (optional)
        """
        self.db_path = db_path
        self.config = config or {}
        self.gemini_model = None

        # Evaluation configuration
        eval_config = self.config.get('evaluation', {})
        self.min_age_days = eval_config.get('min_age_days', 7)
        self.max_age_days = eval_config.get('max_age_days', 21)
        self.top_n = eval_config.get('top_n', 10)

        # AI configuration
        ai_config = self.config.get('ai', {})
        self.model_name = ai_config.get('model_strategy', 'gemini-2.0-flash')
        self.temperature = ai_config.get('temperature', 0.2)

        # Configure Gemini
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini {self.model_name} initialized for recommendation evaluation")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

    def evaluate_recommendations(self, top_n: Optional[int] = None,
                                  min_age_days: Optional[int] = None,
                                  max_age_days: Optional[int] = None) -> Dict:
        """
        Main entry point: evaluate past recommendations against market performance.

        Args:
            top_n: Max recommendations to evaluate (overrides config)
            min_age_days: Min age in days before evaluating (overrides config)
            max_age_days: Max lookback in days (overrides config)

        Returns:
            Summary dict with evaluations and aggregate stats
        """
        top_n = top_n if top_n is not None else self.top_n
        min_age_days = min_age_days if min_age_days is not None else self.min_age_days
        max_age_days = max_age_days if max_age_days is not None else self.max_age_days

        if not YFINANCE_AVAILABLE:
            logger.error("yfinance is required for recommendation evaluation")
            return {'error': 'yfinance not installed', 'evaluations': []}

        # Get eligible recommendations
        eligible = self._get_eligible_recommendations(top_n, min_age_days, max_age_days)

        if not eligible:
            logger.info("No eligible recommendations to evaluate")
            return {
                'evaluations': [],
                'summary': 'No recommendations found in the evaluation window.',
                'total_evaluated': 0
            }

        logger.info(f"📊 Evaluating {len(eligible)} past recommendations...")

        evaluations = []
        for i, rec in enumerate(eligible):
            try:
                evaluation = self._evaluate_single(rec)
                if evaluation:
                    self._write_evaluation(evaluation)
                    evaluations.append(evaluation)
                    logger.info(
                        f"  [{i+1}/{len(eligible)}] {rec['symbol']} "
                        f"{rec['action']} → {evaluation['score']} "
                        f"({evaluation['price_change_pct']:+.1f}%)"
                    )
            except Exception as e:
                logger.error(f"  Failed to evaluate {rec['symbol']}: {e}")

            # Rate limiting for yfinance/Gemini
            if i < len(eligible) - 1:
                time.sleep(1.0)

        if not evaluations and len(eligible) > 0:
             # Check if we failed everything
             return {
                 'evaluations': [],
                 'summary': '❌ Failed to evaluate any recommendations (check logs for yfinance errors).',
                 'total_evaluated': 0,
                 'status': 'failed'
             }

        summary = self._generate_summary(evaluations)
        return summary

    def _get_eligible_recommendations(self, top_n: int,
                                       min_age_days: int,
                                       max_age_days: int) -> List[Dict]:
        """
        Query past BUY/SELL recommendations in the evaluation window,
        excluding already-evaluated ones.
        """
        cutoff_recent = datetime.now(timezone.utc) - timedelta(days=min_age_days)
        cutoff_old = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            self._ensure_table(cursor)

            cursor.execute("""
                SELECT sr.id, sr.symbol, sr.action, sr.confidence,
                       sr.reasoning, sr.target_price, sr.stop_loss, sr.timestamp
                FROM strategy_recommendations sr
                LEFT JOIN recommendation_evaluations re ON sr.id = re.recommendation_id
                WHERE sr.action IN ('BUY', 'SELL')
                AND datetime(sr.timestamp) BETWEEN datetime(?) AND datetime(?)
                AND re.id IS NULL
                ORDER BY sr.confidence DESC, sr.timestamp DESC
                LIMIT ?
            """, (cutoff_old.isoformat(), cutoff_recent.isoformat(), top_n))

            rows = cursor.fetchall()

        return [
            {
                'id': row[0],
                'symbol': row[1],
                'action': row[2],
                'confidence': row[3],
                'reasoning': row[4],
                'target_price': row[5],
                'stop_loss': row[6],
                'timestamp': row[7]
            }
            for row in rows
        ]

    def _evaluate_single(self, rec: Dict) -> Optional[Dict]:
        """Evaluate a single recommendation against actual price data."""
        symbol = rec['symbol']
        rec_date_str = rec['timestamp']

        try:
            rec_date = datetime.fromisoformat(rec_date_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid timestamp for {symbol}: {rec_date_str}")
            return None

        # Fetch price history from recommendation date to now
        price_history = self._fetch_price_history(symbol, rec_date)
        if price_history is None or len(price_history) < 2:
            logger.warning(f"Insufficient price history for {symbol}")
            return None

        # Calculate metrics
        metrics = self._calculate_metrics(rec, price_history)
        if not metrics:
            return None

        # Score the recommendation deterministically
        score = self._score_recommendation(rec, metrics)

        # Generate AI narrative (if available)
        ai_assessment = self._generate_ai_assessment(rec, metrics, score)

        return {
            'recommendation_id': rec['id'],
            'symbol': symbol,
            'original_action': rec['action'],
            'original_confidence': rec['confidence'],
            'original_target_price': rec['target_price'],
            'original_stop_loss': rec['stop_loss'],
            'recommendation_date': rec_date_str,
            'price_at_recommendation': metrics['price_at_recommendation'],
            'price_at_evaluation': metrics['price_at_evaluation'],
            'price_change_pct': metrics['price_change_pct'],
            'target_hit': metrics['target_hit'],
            'stop_loss_hit': metrics['stop_loss_hit'],
            'max_favorable_move_pct': metrics['max_favorable_move_pct'],
            'max_adverse_move_pct': metrics['max_adverse_move_pct'],
            'score': score,
            'ai_assessment': ai_assessment,
            'original_reasoning': rec['reasoning']
        }

    def _fetch_price_history(self, symbol: str, start_date: datetime) -> Optional[List[Dict]]:
        """
        Fetch daily price history from start_date to now using yfinance.

        Returns list of dicts with date, open, high, low, close, volume.
        """
        if not YFINANCE_AVAILABLE:
            return None

        try:
            ticker = yf.Ticker(symbol)
            # Add 7 day buffer before start to ensure we capture the previous close/open
            fetch_start = (start_date - timedelta(days=7)).strftime('%Y-%m-%d')
            df = ticker.history(start=fetch_start)

            if df is None or df.empty:
                logger.warning(f"No yfinance data for {symbol} since {fetch_start}")
                return None

            prices = []
            for idx, row in df.iterrows():
                prices.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })

            return prices

        except Exception as e:
            logger.error(f"yfinance error for {symbol}: {e}")
            return None

    def _calculate_metrics(self, rec: Dict, price_history: List[Dict]) -> Optional[Dict]:
        """
        Calculate performance metrics for a recommendation.

        Returns dict with price changes, max favorable/adverse moves, target/stop hits.
        """
        if not price_history:
            return None

        # Find baseline price (Open of rec date, or Close of prev date)
        rec_date_str = rec['timestamp'][:10] # YYYY-MM-DD
        baseline_price = None

        # Try to find exact date match for Open
        for day in price_history:
            if day['date'] == rec_date_str:
                baseline_price = day['open']
                break

        # If not found (or data starts after), look for closest previous close
        if baseline_price is None:
            # Sort by date just in case
            price_history.sort(key=lambda x: x['date'])
            # Find last day before rec_date
            for day in price_history:
                if day['date'] < rec_date_str:
                    baseline_price = day['close']
                else:
                    break # Passed the date

        # Fallback to first available if still None (though unlikely with buffer)
        if baseline_price is None:
             baseline_price = price_history[0]['open']

        price_at_rec = baseline_price
        price_now = price_history[-1]['close']

        if price_at_rec <= 0:
            return None

        price_change_pct = ((price_now - price_at_rec) / price_at_rec) * 100

        # Calculate max favorable and adverse moves
        price_change_pct = ((price_now - price_at_rec) / price_at_rec) * 100

        # Calculate max favorable and adverse moves
        # Only consider price action ON or AFTER the recommendation date
        evaluation_window = [day for day in price_history if day['date'] >= rec_date_str]
        
        # If rec_date was a weekend, evaluation starts next trading day
        if not evaluation_window:
             # Should not happen as we fetch until now
             evaluation_window = price_history[-1:]

        action = rec['action']
        max_favorable = 0.0
        max_adverse = 0.0

        for day in evaluation_window:
            if action == 'BUY':
                # For BUY: favorable = price went up, adverse = price went down
                high_pct = ((day['high'] - price_at_rec) / price_at_rec) * 100
                low_pct = ((day['low'] - price_at_rec) / price_at_rec) * 100
                max_favorable = max(max_favorable, high_pct)
                max_adverse = min(max_adverse, low_pct)
            elif action == 'SELL':
                # For SELL: favorable = price went down, adverse = price went up
                low_pct = ((price_at_rec - day['low']) / price_at_rec) * 100
                high_pct = ((day['high'] - price_at_rec) / price_at_rec) * 100
                max_favorable = max(max_favorable, low_pct)
                max_adverse = min(max_adverse, -high_pct)

        # Check target and stop loss hits
        target_hit = 0
        stop_loss_hit = 0
        target_price = rec.get('target_price')
        stop_loss = rec.get('stop_loss')

        for day in evaluation_window:
            if action == 'BUY':
                if target_price and day['high'] >= target_price:
                    target_hit = 1
                if stop_loss and day['low'] <= stop_loss:
                    stop_loss_hit = 1
            elif action == 'SELL':
                if target_price and day['low'] <= target_price:
                    target_hit = 1
                if stop_loss and day['high'] >= stop_loss:
                    stop_loss_hit = 1

        return {
            'price_at_recommendation': price_at_rec,
            'price_at_evaluation': price_now,
            'price_change_pct': round(price_change_pct, 2),
            'max_favorable_move_pct': round(max_favorable, 2),
            'max_adverse_move_pct': round(max_adverse, 2),
            'target_hit': target_hit,
            'stop_loss_hit': stop_loss_hit
        }

    def _score_recommendation(self, rec: Dict, metrics: Dict) -> str:
        """
        Deterministic scoring of a recommendation based on outcome.

        Returns: 'excellent', 'good', 'neutral', 'poor', or 'bad'
        """
        action = rec['action']
        pct = metrics['price_change_pct']
        target_hit = metrics['target_hit']
        stop_hit = metrics['stop_loss_hit']

        if action == 'BUY':
            if target_hit:
                return 'excellent'
            elif pct >= 5.0:
                return 'good'
            elif pct >= -2.0:
                return 'neutral'
            elif pct >= -5.0 and not stop_hit:
                return 'poor'
            else:
                return 'bad'
        elif action == 'SELL':
            if target_hit:
                return 'excellent'
            elif pct <= -5.0:
                return 'good'
            elif pct <= 2.0:
                return 'neutral'
            elif pct <= 5.0 and not stop_hit:
                return 'poor'
            else:
                return 'bad'

        return 'neutral'

    def _generate_ai_assessment(self, rec: Dict, metrics: Dict, score: str) -> Optional[str]:
        """Generate an AI narrative explaining why the recommendation was good or bad."""
        if not self.gemini_model:
            return self._fallback_assessment(rec, metrics, score)

        prompt = f"""You are a trading performance analyst reviewing a past recommendation.

**Original Recommendation:**
- Symbol: {rec['symbol']}
- Action: {rec['action']}
- Confidence: {rec['confidence']:.0%}
- Reasoning: {rec.get('reasoning', 'N/A')}
- Target Price: {f"${rec['target_price']:.2f}" if rec.get('target_price') else 'N/A'}
- Stop Loss: {f"${rec['stop_loss']:.2f}" if rec.get('stop_loss') else 'N/A'}
- Date: {rec['timestamp'][:10]}

**Actual Performance:**
- Price at recommendation: ${metrics['price_at_recommendation']:.2f}
- Current price: ${metrics['price_at_evaluation']:.2f}
- Price change: {metrics['price_change_pct']:+.1f}%
- Max favorable move: {metrics['max_favorable_move_pct']:+.1f}%
- Max adverse move: {metrics['max_adverse_move_pct']:+.1f}%
- Target hit: {'Yes' if metrics['target_hit'] else 'No'}
- Stop loss hit: {'Yes' if metrics['stop_loss_hit'] else 'No'}
- Score: {score.upper()}

**Task:** Write a concise 2-3 sentence assessment explaining:
1. Whether the recommendation was good and why
2. What the trader should learn from this outcome

Be specific about the numbers. Output ONLY the assessment text, no JSON or formatting."""

        def make_call():
            return self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=300
                )
            )

        response = call_with_retry(make_call, context=f"eval-{rec['symbol']}")
        if response:
            return response.text.strip()

        return self._fallback_assessment(rec, metrics, score)

    def _fallback_assessment(self, rec: Dict, metrics: Dict, score: str) -> str:
        """Generate a simple rule-based assessment when AI is unavailable."""
        symbol = rec['symbol']
        action = rec['action']
        pct = metrics['price_change_pct']

        if action == 'BUY':
            if score in ('excellent', 'good'):
                return (f"{symbol} {action} was a {score} call. "
                        f"Price moved {pct:+.1f}% in the right direction"
                        f"{', hitting target' if metrics['target_hit'] else ''}.")
            elif score == 'neutral':
                return (f"{symbol} {action} was neutral. Price moved {pct:+.1f}%, "
                        f"essentially flat since the recommendation.")
            else:
                return (f"{symbol} {action} was a {score} call. "
                        f"Price declined {pct:+.1f}%"
                        f"{', triggering stop loss' if metrics['stop_loss_hit'] else ''}.")
        else:  # SELL
            if score in ('excellent', 'good'):
                return (f"{symbol} {action} was a {score} call. "
                        f"Price dropped {abs(pct):.1f}% confirming the bearish thesis.")
            elif score == 'neutral':
                return (f"{symbol} {action} was neutral. Price moved {pct:+.1f}%, "
                        f"neither confirming nor refuting the sell signal.")
            else:
                return (f"{symbol} {action} was a {score} call. "
                        f"Price rose {pct:+.1f}%, moving against the recommendation.")

    def _ensure_table(self, cursor):
        """Ensure recommendation_evaluations table exists (for incremental migrations)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER NOT NULL UNIQUE,
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
            )
        """)

    def _write_evaluation(self, evaluation: Dict):
        """Persist evaluation result to database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            self._ensure_table(cursor)

            cursor.execute("""
                INSERT INTO recommendation_evaluations
                (recommendation_id, symbol, original_action, original_confidence,
                 original_target_price, original_stop_loss, recommendation_date,
                 price_at_recommendation, price_at_evaluation, price_change_pct,
                 target_hit, stop_loss_hit, max_favorable_move_pct, max_adverse_move_pct,
                 score, ai_assessment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                evaluation['recommendation_id'],
                evaluation['symbol'],
                evaluation['original_action'],
                evaluation['original_confidence'],
                evaluation.get('original_target_price'),
                evaluation.get('original_stop_loss'),
                evaluation['recommendation_date'],
                evaluation['price_at_recommendation'],
                evaluation['price_at_evaluation'],
                evaluation['price_change_pct'],
                evaluation['target_hit'],
                evaluation['stop_loss_hit'],
                evaluation['max_favorable_move_pct'],
                evaluation['max_adverse_move_pct'],
                evaluation['score'],
                evaluation.get('ai_assessment')
            ))

            conn.commit()

        logger.debug(f"Wrote evaluation for {evaluation['symbol']} to database")

    def _generate_summary(self, evaluations: List[Dict]) -> Dict:
        """
        Generate aggregate summary of all evaluations.

        Returns dict with evaluations list, stats, and text summary.
        """
        if not evaluations:
            return {
                'evaluations': [],
                'summary': 'No recommendations were evaluated.',
                'total_evaluated': 0
            }

        total = len(evaluations)
        score_counts = {'excellent': 0, 'good': 0, 'neutral': 0, 'poor': 0, 'bad': 0}
        total_pct_change = 0.0
        target_hits = 0
        stop_hits = 0

        for e in evaluations:
            score_counts[e['score']] = score_counts.get(e['score'], 0) + 1
            total_pct_change += e['price_change_pct']
            if e['target_hit']:
                target_hits += 1
            if e['stop_loss_hit']:
                stop_hits += 1

        avg_pct_change = total_pct_change / total if total > 0 else 0
        positive_rate = sum(1 for e in evaluations
                           if (e['original_action'] == 'BUY' and e['price_change_pct'] > 0)
                           or (e['original_action'] == 'SELL' and e['price_change_pct'] < 0)) / total * 100

        # Find best and worst using direction-normalized score
        def _direction_score(e):
            """Normalize performance: positive = favorable for the recommended action."""
            if e['original_action'] == 'SELL':
                return -e['price_change_pct']
            return e['price_change_pct']

        best = max(evaluations, key=_direction_score)
        worst = min(evaluations, key=_direction_score)

        def _display_pct(e):
            """Display direction-normalized percentage for clarity."""
            return _direction_score(e)

        # Build text summary
        summary_lines = [
            f"📊 Recommendation Evaluation Summary ({total} recommendations)",
            f"",
            f"Score Distribution:",
            f"  🏆 Excellent: {score_counts['excellent']}  "
            f"✅ Good: {score_counts['good']}  "
            f"➖ Neutral: {score_counts['neutral']}  "
            f"⚠️ Poor: {score_counts['poor']}  "
            f"❌ Bad: {score_counts['bad']}",
            f"",
            f"Hit Rate: {positive_rate:.0f}% of recommendations moved in the right direction",
            f"Avg Price Change: {avg_pct_change:+.1f}%",
            f"Targets Hit: {target_hits}/{total}  |  Stops Hit: {stop_hits}/{total}",
            f"",
            f"Best: {best['symbol']} ({best['original_action']}) → {_display_pct(best):+.1f}% (direction-adjusted)",
            f"Worst: {worst['symbol']} ({worst['original_action']}) → {_display_pct(worst):+.1f}% (direction-adjusted)",
        ]

        # Add individual assessments
        summary_lines.append("")
        summary_lines.append("Individual Assessments:")
        for e in evaluations:
            icon = {'excellent': '🏆', 'good': '✅', 'neutral': '➖',
                    'poor': '⚠️', 'bad': '❌'}.get(e['score'], '❓')
            summary_lines.append(
                f"  {icon} {e['symbol']} {e['original_action']} "
                f"({e['recommendation_date'][:10]}): "
                f"{e['price_change_pct']:+.1f}% — {e.get('ai_assessment', 'No assessment')}"
            )

        summary_text = "\n".join(summary_lines)
        logger.info(f"\n{summary_text}")

        return {
            'evaluations': evaluations,
            'summary': summary_text,
            'total_evaluated': total,
            'stats': {
                'score_distribution': score_counts,
                'positive_rate_pct': round(positive_rate, 1),
                'avg_price_change_pct': round(avg_pct_change, 2),
                'targets_hit': target_hits,
                'stops_hit': stop_hits,
                'best': {'symbol': best['symbol'], 'action': best['original_action'],
                         'pct': best['price_change_pct']},
                'worst': {'symbol': worst['symbol'], 'action': worst['original_action'],
                          'pct': worst['price_change_pct']}
            }
        }

    def get_recent_evaluations(self, symbol: Optional[str] = None,
                                limit: int = 20) -> List[Dict]:
        """Get recent evaluation results from database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            try:
                if symbol:
                    cursor.execute("""
                        SELECT recommendation_id, symbol, original_action, original_confidence,
                               original_target_price, original_stop_loss, recommendation_date,
                               evaluation_date, price_at_recommendation, price_at_evaluation,
                               price_change_pct, target_hit, stop_loss_hit,
                               max_favorable_move_pct, max_adverse_move_pct, score, ai_assessment
                        FROM recommendation_evaluations
                        WHERE symbol = ?
                        ORDER BY evaluation_date DESC
                        LIMIT ?
                    """, (symbol.upper(), limit))
                else:
                    cursor.execute("""
                        SELECT recommendation_id, symbol, original_action, original_confidence,
                               original_target_price, original_stop_loss, recommendation_date,
                               evaluation_date, price_at_recommendation, price_at_evaluation,
                               price_change_pct, target_hit, stop_loss_hit,
                               max_favorable_move_pct, max_adverse_move_pct, score, ai_assessment
                        FROM recommendation_evaluations
                        ORDER BY evaluation_date DESC
                        LIMIT ?
                    """, (limit,))

                rows = cursor.fetchall()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    logger.debug(f"Evaluations table missing, returning empty list: {e}")
                    return []
                raise
            except Exception as e:
                if "no such table" in str(e):
                    # Fallback for non-sqlite3.OperationalError variants (e.g. turso)
                    return []
                raise

        return [
            {
                'recommendation_id': row[0],
                'symbol': row[1],
                'original_action': row[2],
                'original_confidence': row[3],
                'original_target_price': row[4],
                'original_stop_loss': row[5],
                'recommendation_date': row[6],
                'evaluation_date': row[7],
                'price_at_recommendation': row[8],
                'price_at_evaluation': row[9],
                'price_change_pct': row[10],
                'target_hit': row[11],
                'stop_loss_hit': row[12],
                'max_favorable_move_pct': row[13],
                'max_adverse_move_pct': row[14],
                'score': row[15],
                'ai_assessment': row[16]
            }
            for row in rows
        ]
