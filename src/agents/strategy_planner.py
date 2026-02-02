"""
Strategy Planner Agent

Synthesizes all inputs and generates trade recommendations using AI reasoning.
Handles:
- Context gathering from database (prices, news, portfolio)
- Chain-of-Thought prompting for transparent reasoning
- Confidence scoring for recommendations
"""


from src.data.db_connection import get_connection
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
    logger.warning("google-generativeai not installed. AI features will be limited.")


class StrategyPlanner:
    """Agent responsible for AI-powered trade recommendation synthesis."""
    
    def __init__(self, db_path: str, gemini_key: Optional[str] = None, 
                 config: Optional[Dict] = None):
        """
        Initialize Strategy Planner.
        
        Args:
            db_path: Path to SQLite database
            gemini_key: Google Gemini API key (optional)
            config: Configuration dict (optional)
        """
        self.db_path = db_path
        self.config = config or {}
        self.gemini_model = None
        
        # AI configuration
        ai_config = self.config.get('ai', {})
        self.model_name = ai_config.get('model_strategy', 'gemini-2.0-flash')
        self.temperature = ai_config.get('temperature', 0.3)
        
        # Configure Gemini with configured model
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini {self.model_name} initialized for strategy planning")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
    
    def generate_recommendation(self, symbol: str) -> Optional[Dict]:
        """
        Generate a trade recommendation for a specific symbol.
        Uses Chain-of-Thought prompting for transparency.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Recommendation dict or None if failed
        """
        # Gather context from database
        context = self._gather_context(symbol)

        if context.get('market_data_stale'):
            logger.warning(f"Skipping {symbol}: market data is stale (run market scan first)")
            return None

        if not context.get('price'):
            logger.warning(f"No price data available for {symbol}")
            return None
        
        if not self.gemini_model:
            logger.warning("Gemini not configured, using fallback recommendation")
            return self._fallback_recommendation(symbol, context)
        
        # Construct prompt
        prompt = self._build_cot_prompt(symbol, context)
        
        def make_call():
            return self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=1000
                )
            )
        
        response = call_with_retry(make_call, context=symbol)
        
        if response:
            result = self._parse_json_response(response.text)
            if result:
                result['symbol'] = symbol
                result['timestamp'] = datetime.now().isoformat()
                self._write_to_db(result)
                return result
            else:
                logger.warning(f"Failed to parse recommendation for {symbol}")
        
        return self._fallback_recommendation(symbol, context)
    
    def generate_batch_recommendations(self, symbols: List[str]) -> List[Dict]:
        """
        Generate recommendations for multiple symbols.
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            List of recommendation dicts
        """
        recommendations = []
        
        for i, symbol in enumerate(symbols):
            rec = self.generate_recommendation(symbol)
            if rec:
                recommendations.append(rec)
            
            # Rate limiting: 1s delay to avoid per-second burst limits
            if i < len(symbols) - 1:
                time.sleep(1.0)
        
        return recommendations
    
    def review_holdings(self) -> List[Dict]:
        """
        Explicitly review all current holdings for sell opportunities.
        
        Uses a sell-focused analysis perspective, particularly for
        overweight or profitable positions that might benefit from rebalancing.
        
        Returns:
            List of recommendation dicts for held positions
        """
        # Get current holdings from database

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT h.symbol, h.quantity, h.current_value
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                WHERE p.id = (SELECT id FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 1)
                AND h.quantity > 0
            """)
            
            holdings = cursor.fetchall()
        
        if not holdings:
            logger.info("No holdings to review")
            return []
        
        logger.info(f"📊 Reviewing {len(holdings)} holdings for sell opportunities...")
        
        recommendations = []
        for i, (symbol, qty, value) in enumerate(holdings):
            logger.info(f"  Reviewing {symbol}: {qty:.0f} shares (${value:,.2f})")
            
            rec = self.generate_recommendation(symbol)
            if rec:
                recommendations.append(rec)
            
            # Rate limiting
            if i < len(holdings) - 1:
                time.sleep(1.0)
        
        return recommendations
    
    def _gather_context(self, symbol: str) -> Dict:
        """Pull all relevant data from database."""
        # Market data TTL: 24 hours (configurable)
        market_data_ttl_hours = self.config.get('limits', {}).get('strategy_data_ttl_hours', 24)

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Get latest price data with timestamp for TTL check
            cursor.execute("""
                SELECT price, atr, sma_50, is_volatile, timestamp
                FROM market_data
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol.upper(),))
            market_row = cursor.fetchone()

            # Check if market data is stale
            market_data = None
            market_data_stale = False
            if market_row:
                try:
                    data_timestamp = datetime.fromisoformat(market_row[4])
                    age = datetime.now() - data_timestamp
                    if age > timedelta(hours=market_data_ttl_hours):
                        market_data_stale = True
                        logger.warning(f"Market data for {symbol} is stale ({age.total_seconds()/3600:.1f}h old)")
                    else:
                        market_data = market_row[:4]  # price, atr, sma_50, is_volatile
                except Exception as e:
                    logger.error(f"Failed to parse market data timestamp for {symbol}: {e}")
                    market_data = market_row[:4]  # Use data anyway if timestamp parsing fails
            
            # Get recent news sentiment (only from last 72 hours)
            # Use datetime() to parse ISO timestamps (which have 'T' separator)
            news_recency_hours = 72
            cursor.execute("""
                SELECT sentiment, confidence, implied_action, key_reason
                FROM news_analysis
                WHERE symbol = ?
                AND datetime(timestamp) > datetime('now', ?)
                ORDER BY timestamp DESC
                LIMIT 5
            """, (symbol.upper(), f'-{news_recency_hours} hours'))
            news_items = cursor.fetchall()
            
            # Get current portfolio position (if any)
            cursor.execute("""
                SELECT h.quantity, h.cost_basis, h.current_value
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                WHERE h.symbol = ?
                ORDER BY p.import_timestamp DESC
                LIMIT 1
            """, (symbol.upper(),))
            position = cursor.fetchone()
            
            # Get total portfolio equity
            cursor.execute("""
                SELECT total_equity, cash_balance
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 1
            """)
            portfolio = cursor.fetchone()
        
        return {
            'price': market_data[0] if market_data else None,
            'atr': market_data[1] if market_data else None,
            'sma_50': market_data[2] if market_data else None,
            'is_volatile': bool(market_data[3]) if market_data else False,
            'market_data_stale': market_data_stale,
            'news_sentiment': [
                {'sentiment': n[0], 'confidence': n[1], 'action': n[2], 'reason': n[3]}
                for n in news_items
            ] if news_items else [],
            'current_position': {
                'quantity': position[0] if position else 0,
                'cost_basis': position[1] if position else None,
                'current_value': position[2] if position else None
            },
            'portfolio_equity': portfolio[0] if portfolio else 10000,
            'cash_balance': portfolio[1] if portfolio else 10000
        }
    
    def _build_cot_prompt(self, symbol: str, context: Dict) -> str:
        """Build Chain-of-Thought prompt to force reasoning transparency."""
        
        # Format numbers safely
        price = context.get('price', 0) or 0
        sma_50 = context.get('sma_50')
        atr = context.get('atr')
        
        sma_str = f"${sma_50:.2f}" if sma_50 else "N/A"
        atr_str = f"${atr:.2f}" if atr else "N/A"
        
        position = context.get('current_position', {})
        position_qty = position.get('quantity', 0)
        cost_basis = position.get('cost_basis')
        position_value = position.get('current_value', 0) or 0
        portfolio_equity = context.get('portfolio_equity', 10000)
        
        # Calculate position weight and P/L
        position_pct = (position_value / portfolio_equity * 100) if portfolio_equity > 0 else 0
        is_overweight = position_pct > 20
        
        # Calculate unrealized P/L
        if cost_basis and position_qty > 0 and price > 0:
            total_cost = cost_basis * position_qty
            unrealized_pl = position_value - total_cost
            unrealized_pl_pct = (unrealized_pl / total_cost * 100) if total_cost > 0 else 0
            pl_str = f"${unrealized_pl:+,.2f} ({unrealized_pl_pct:+.1f}%)"
        else:
            unrealized_pl_pct = 0
            pl_str = "N/A"
        
        cost_str = f"${cost_basis:.2f}" if cost_basis else "N/A"
        
        # Build position section based on whether they hold the stock
        if position_qty > 0:
            position_section = f"""**Current Position in {symbol}:**
- Shares Held: {position_qty:,.0f}
- Cost Basis: {cost_str}
- Current Value: ${position_value:,.2f}
- Position Size: {position_pct:.1f}% of portfolio
- Unrealized P/L: {pl_str}
- OVERWEIGHT: {'⚠️ YES - Consider rebalancing' if is_overweight else 'No'}"""
        else:
            position_section = f"**Current Position in {symbol}:** None (considering new entry)"
        
        # Build profit-taking guidance
        profit_guidance = ""
        if position_qty > 0:
            profit_guidance = """
**Important - Existing Position Guidance:**
- If position is >20% of portfolio, STRONGLY consider SELL to rebalance
- If unrealized gain >20%, consider partial profit-taking
- Evaluate honestly: Should you ADD more, HOLD, or SELL some/all?
- Don't let winners become losers - protect gains on large positions"""
        
        prompt = f"""You are a Senior Financial Analyst evaluating a trade opportunity.

**Task:** Analyze {symbol} and decide on an action.

**Market Data:**
- Current Price: ${price:.2f}
- 50-Day SMA: {sma_str}
- ATR (Volatility): {atr_str}
- High Volatility Warning: {'YES' if context.get('is_volatile') else 'NO'}

**Recent News Sentiment:**
{self._format_news(context.get('news_sentiment', []))}

**Portfolio Context:**
- Total Equity: ${portfolio_equity:,.2f}
- Cash Available: ${context.get('cash_balance', 10000):,.2f}

{position_section}
{profit_guidance}

**Instructions:**
Use the following step-by-step reasoning process:

**Step 1: Technical Analysis**
Evaluate the price trend. Is it above/below SMA? Is momentum clear?

**Step 2: Sentiment Analysis**
Review the news. Is there a clear catalyst? What's the consensus?

**Step 3: Portfolio Risk**
Check position sizing. Is this position overweight? Should you rebalance?

**Step 4: Final Recommendation**
Based on the above, what action do you recommend?

{"**Valid Actions:** BUY (add to position), SELL (reduce/exit), or HOLD (maintain current position)" if position_qty > 0 else "**Valid Actions:** BUY (open new position) or SKIP (not worth buying now)"}

**Output Format (JSON ONLY, no preamble, no markdown code blocks):**
{{
  "step1_technical": "Your technical analysis in 20 words",
  "step2_sentiment": "Your sentiment analysis in 20 words",
  "step3_risk": "Your risk assessment in 20 words",
  "action": "{"BUY | SELL | HOLD" if position_qty > 0 else "BUY | SKIP"}",
  "confidence": 0.0-1.0,
  "reasoning": "Final justification in 30 words",
  "target_price": null or number (for BUY/SELL),
  "stop_loss": null or number (for BUY)
}}"""
        return prompt
    
    def _format_news(self, news_items: List[Dict]) -> str:
        """Format news for prompt."""
        if not news_items:
            return "No recent significant news."
        
        formatted = []
        for item in news_items:
            confidence = item.get('confidence', 0)
            formatted.append(
                f"- {item['sentiment'].upper()} (confidence: {confidence:.0%}): {item.get('reason', 'N/A')}"
            )
        return "\n".join(formatted)
    
    def _parse_json_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from Gemini response."""
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code block
        text = response_text.strip()
        if '```' in text:
            lines = text.split('\n')
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith('```') and not in_json:
                    in_json = True
                    continue
                elif line.startswith('```') and in_json:
                    break
                elif in_json:
                    json_lines.append(line)
            
            try:
                return json.loads('\n'.join(json_lines))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"Failed to parse JSON: {response_text[:200]}...")
        return None
    
    def _fallback_recommendation(self, symbol: str, context: Dict) -> Dict:
        """Generate simple rule-based recommendation when AI unavailable."""
        price = context.get('price', 0)
        sma_50 = context.get('sma_50')
        atr = context.get('atr')
        position_qty = context.get('current_position', {}).get('quantity', 0)
        is_volatile = context.get('is_volatile', False)
        
        # Default action and reasoning
        if position_qty > 0:
            action = 'HOLD'
            reasoning = "Maintaining current position pending further analysis"
        else:
            action = 'SKIP'
            reasoning = "Insufficient data - not recommended for new entry"
        
        # If we have SMA, use traditional SMA-based signals
        if price and sma_50:
            if price > sma_50 and position_qty == 0:
                action = 'BUY'
                reasoning = f"Price ${price:.2f} above 50-day SMA ${sma_50:.2f}, no current position"
            elif price < sma_50 and position_qty > 0:
                action = 'SELL'
                reasoning = f"Price ${price:.2f} below 50-day SMA ${sma_50:.2f}, consider taking profits"
        
        # Fallback: If no SMA but we have price and low volatility, consider BUY for screened stocks
        elif price and price > 0 and position_qty == 0 and not is_volatile:
            # These stocks were pre-screened by Alpaca's screener, so they have momentum
            # If they're not too volatile, they might be worth buying
            action = 'BUY'
            confidence = 0.4  # Slightly higher confidence than pure SKIP
            reasoning = f"Screened stock at ${price:.2f} with manageable volatility - potential entry"
            
            return {
                'symbol': symbol,
                'step1_technical': 'Rule-based analysis (AI unavailable, no SMA data)',
                'step2_sentiment': 'No sentiment analysis available',
                'step3_risk': 'Pre-screened by Alpaca momentum filter',
                'action': action,
                'confidence': confidence,
                'reasoning': reasoning,
                'target_price': None,
                'stop_loss': None,
                'timestamp': datetime.now().isoformat()
            }
        
        return {
            'symbol': symbol,
            'step1_technical': 'Rule-based analysis (AI unavailable)',
            'step2_sentiment': 'No sentiment analysis available',
            'step3_risk': 'Manual risk review recommended',
            'action': action,
            'confidence': 0.3,  # Low confidence for rule-based
            'reasoning': reasoning,
            'target_price': None,
            'stop_loss': None,
            'timestamp': datetime.now().isoformat()
        }
    
    def _write_to_db(self, recommendation: Dict):
        """Store recommendation for audit trail."""
        # Safety check: Database schema constraint only allows specific actions
        allowed_actions = {'BUY', 'SELL', 'HOLD'}
        if recommendation['action'] not in allowed_actions:
            logger.debug(f"Skipping DB write for action '{recommendation['action']}' (not in schema)")
            return

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO strategy_recommendations
                (symbol, action, confidence, reasoning, target_price, stop_loss, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                recommendation['symbol'],
                recommendation['action'],
                recommendation['confidence'],
                recommendation.get('reasoning'),
                recommendation.get('target_price'),
                recommendation.get('stop_loss'),
                recommendation['timestamp']
            ))
            
            conn.commit()
            
        logger.debug(f"Wrote recommendation for {recommendation['symbol']} to database")
    
    def get_recent_recommendations(self, symbol: Optional[str] = None, 
                                    limit: int = 10) -> List[Dict]:
        """Get recent recommendations from database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("""
                    SELECT symbol, action, confidence, reasoning, target_price, stop_loss, timestamp
                    FROM strategy_recommendations
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (symbol.upper(), limit))
            else:
                cursor.execute("""
                    SELECT symbol, action, confidence, reasoning, target_price, stop_loss, timestamp
                    FROM strategy_recommendations
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
        
        return [
            {
                'symbol': row[0],
                'action': row[1],
                'confidence': row[2],
                'reasoning': row[3],
                'target_price': row[4],
                'stop_loss': row[5],
                'timestamp': row[6]
            }
            for row in rows
        ]
