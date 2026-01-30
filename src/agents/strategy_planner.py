"""
Strategy Planner Agent

Synthesizes all inputs and generates trade recommendations using AI reasoning.
Handles:
- Context gathering from database (prices, news, portfolio)
- Chain-of-Thought prompting for transparent reasoning
- Confidence scoring for recommendations
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import time

from utils.gemini_client import call_with_retry

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
    
    def __init__(self, db_path: str, gemini_key: Optional[str] = None):
        """
        Initialize Strategy Planner.
        
        Args:
            db_path: Path to SQLite database
            gemini_key: Google Gemini API key (optional)
        """
        self.db_path = db_path
        self.gemini_model = None
        
        # Configure Gemini with Pro model for reasoning
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
                logger.info("Gemini Pro model initialized for strategy planning")
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
                    temperature=0.3,
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
    
    def _gather_context(self, symbol: str) -> Dict:
        """Pull all relevant data from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest price data
        cursor.execute("""
            SELECT price, atr, sma_50, is_volatile 
            FROM market_data 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (symbol.upper(),))
        market_data = cursor.fetchone()
        
        # Get recent news sentiment
        cursor.execute("""
            SELECT sentiment, confidence, implied_action, key_reason
            FROM news_analysis
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (symbol.upper(),))
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
        
        conn.close()
        
        return {
            'price': market_data[0] if market_data else None,
            'atr': market_data[1] if market_data else None,
            'sma_50': market_data[2] if market_data else None,
            'is_volatile': bool(market_data[3]) if market_data else False,
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
        cost_str = f"${cost_basis:.2f}" if cost_basis else "N/A"
        
        prompt = f"""You are a Senior Financial Analyst evaluating a trade opportunity.

**Task:** Analyze whether to BUY, SELL, or HOLD {symbol}.

**Market Data:**
- Current Price: ${price:.2f}
- 50-Day SMA: {sma_str}
- ATR (Volatility): {atr_str}
- High Volatility Warning: {'YES' if context.get('is_volatile') else 'NO'}

**Recent News Sentiment:**
{self._format_news(context.get('news_sentiment', []))}

**Current Portfolio Context:**
- Total Equity: ${context.get('portfolio_equity', 10000):,.2f}
- Cash Available: ${context.get('cash_balance', 10000):,.2f}
- Existing Position in {symbol}: {position_qty} shares @ {cost_str}

**Instructions:**
Use the following step-by-step reasoning process:

**Step 1: Technical Analysis**
Evaluate the price trend. Is it above/below SMA? Is momentum clear?

**Step 2: Sentiment Analysis**
Review the news. Is there a clear catalyst? What's the consensus?

**Step 3: Portfolio Risk**
Check position sizing. Would this trade create over-concentration?

**Step 4: Final Recommendation**
Based on the above, what action do you recommend?

**Output Format (JSON ONLY, no preamble, no markdown code blocks):**
{{
  "step1_technical": "Your technical analysis in 20 words",
  "step2_sentiment": "Your sentiment analysis in 20 words",
  "step3_risk": "Your risk assessment in 20 words",
  "action": "BUY" | "SELL" | "HOLD",
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
        position_qty = context.get('current_position', {}).get('quantity', 0)
        
        # Simple logic: 
        # - Above SMA50 and no position = potential BUY
        # - Below SMA50 and has position = potential SELL
        # - Otherwise HOLD
        
        action = 'HOLD'
        reasoning = "Insufficient data for recommendation"
        
        if price and sma_50:
            if price > sma_50 and position_qty == 0:
                action = 'BUY'
                reasoning = f"Price ${price:.2f} above 50-day SMA ${sma_50:.2f}, no current position"
            elif price < sma_50 and position_qty > 0:
                action = 'SELL'
                reasoning = f"Price ${price:.2f} below 50-day SMA ${sma_50:.2f}, consider taking profits"
        
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
        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        
        logger.debug(f"Wrote recommendation for {recommendation['symbol']} to database")
    
    def get_recent_recommendations(self, symbol: Optional[str] = None, 
                                    limit: int = 10) -> List[Dict]:
        """Get recent recommendations from database."""
        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        
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
