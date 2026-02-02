"""
Trade Advisor Agent

Answers natural language questions about trades using AI.
Gathers context from portfolio, news, market data, and past recommendations
to provide informed suggestions with confidence levels.
"""


from src.data.db_connection import get_connection
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Try to import Google Generative AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Trade advisor will be limited.")

from src.utils.gemini_client import call_with_retry


class TradeAdvisor:
    """Agent that answers natural language questions about trades."""
    
    def __init__(self, db_path: str, gemini_key: Optional[str] = None, 
                 config: Optional[Dict] = None, market_analyst: Any = None):
        """
        Initialize Trade Advisor.
        
        Args:
            db_path: Path to SQLite database
            gemini_key: Google Gemini API key
            config: Configuration dict
            market_analyst: MarketAnalyst instance for on-demand fetching
        """
        self.db_path = db_path
        self.config = config or {}
        self.market_analyst = market_analyst
        self.gemini_model = None
        
        # AI configuration
        ai_config = self.config.get('ai', {})
        self.model_name = ai_config.get('model_strategy', 'gemini-2.0-flash')
        self.temperature = ai_config.get('temperature', 0.3)
        
        # Configure Gemini
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini {self.model_name} initialized for Trade Advisor")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

    def ask(self, question: str) -> Dict:
        """
        Answer a natural language question about trades.
        
        Args:
            question: User's question (e.g., "Should I sell 100 shares of MSFT at 480?")
            
        Returns:
            Dict with recommendation, confidence, analysis, and reasoning
        """
        if not self.gemini_model:
            return {
                'recommendation': 'ERROR',
                'confidence': 0.0,
                'analysis': ['AI model not available'],
                'reasoning': 'Cannot process question without AI model configured.',
                'symbol': None,
                'action': None
            }
        
        # Extract intent from question
        intent = self._extract_intent(question)
        symbol = intent.get('symbol')
        
        # Gather context
        context = self._gather_context(symbol) if symbol else self._gather_portfolio_context()
        
        # Build prompt
        prompt = self._build_prompt(question, intent, context)
        
        # Call LLM
        def make_call():
            return self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=2000
                )
            )
        
        response = call_with_retry(make_call, context=f"trade_advisor:{symbol or 'portfolio'}")
        
        if response and response.text:
            result = self._parse_response(response.text)
            result['symbol'] = symbol
            result['action'] = intent.get('action')
            return result
        
        return {
            'recommendation': 'ERROR',
            'confidence': 0.0,
            'analysis': ['Failed to get AI response'],
            'reasoning': 'The AI model did not return a valid response.',
            'symbol': symbol,
            'action': intent.get('action')
        }
    
    def _extract_intent(self, question: str) -> Dict:
        """
        Parse the question to extract symbol, action, quantity, and price.
        
        Uses regex patterns to identify common trading question patterns.
        Quantity must be associated with 'shares'. Price must follow 'at/@/$'.
        """
        intent = {
            'symbol': None,
            'action': None,
            'quantity': None,
            'price': None
        }
        
        question_upper = question.upper()
        
        # Common words to exclude from symbol matching
        exclude_words = {'I', 'A', 'IF', 'OF', 'AT', 'THE', 'MY', 'DO', 'IS', 'IT', 
                        'TO', 'OR', 'AN', 'BE', 'IN', 'ON', 'FOR', 'AND', 'YOU', 
                        'WHAT', 'SHOULD', 'THINK', 'SELL', 'BUY', 'HOLD', 'GOOD',

                        'TIME', 'NOW', 'MORE', 'SOME', 'ALL', 'SHARE', 'SHARES',
                        'PRICE', 'TODAY', 'WEEK', 'YEAR', 'MONTH', 'DAY', 'DATE'}
        
        # Find all potential symbols and pick the first valid one
        all_matches = re.findall(r'\b([A-Z]{1,5}(?:[.\-][A-Z]{1,2})?)\b', question_upper)
        for match in all_matches:
            if match not in exclude_words and len(match) >= 2:
                intent['symbol'] = match
                break
        # Extract action first (so we know if it's missing)
        if any(word in question_upper for word in ['SELL', 'SELLING', 'SOLD']):
            intent['action'] = 'SELL'
        elif any(word in question_upper for word in ['BUY', 'BUYING', 'BOUGHT', 'PURCHASE']):
            intent['action'] = 'BUY'
        elif any(word in question_upper for word in ['HOLD', 'KEEP', 'HOLDING']):
            intent['action'] = 'HOLD'


        
        # Extract quantity - must be followed by 'share(s)' to avoid grabbing prices
        qty_match = re.search(r'(\d+)\s+shares?', question, re.IGNORECASE)
        if qty_match:
            intent['quantity'] = int(qty_match.group(1))
        
        # Extract price - must be preceded by 'at', '@', or '$'
        # 'for' only counts if followed by '$' (e.g., 'for $150' not 'for 100 shares')
        price_match = re.search(r'(?:at|@)\s*\$?\s*(\d+(?:\.\d{1,2})?)|\$(\d+(?:\.\d{1,2})?)', question, re.IGNORECASE)
        if price_match:
            # Get whichever group matched
            price_str = price_match.group(1) or price_match.group(2)
            if price_str:
                intent['price'] = float(price_str)
        
        
        # Fallback/Enhancement: If no symbol found via regex, OR if we want AI refinement for missing fields
        # Trigger if:
        # 1. No symbol found
        # 2. Symbol found but no Action (AI can infer "dump" = "sell")
        # 3. Only if AI model is available
        # NOTE: We do NOT trigger for missing Quantity/Price to save latency, as they are optional.
        missing_critical = not intent['symbol'] or not intent['action']
        
        if missing_critical and self.gemini_model:
            ai_intent = self._resolve_intent_with_ai(question)
            
            # Merge AI intent into regex intent (AI fills gaps)
            if ai_intent.get('symbol'):
                intent['symbol'] = ai_intent['symbol']
            if not intent['action'] and ai_intent.get('action'):
                intent['action'] = ai_intent['action']
            # Only override quantity/price if regex didn't find them and they are in AI result
            if not intent['quantity'] and ai_intent.get('quantity'):
                intent['quantity'] = ai_intent['quantity']
            if not intent['price'] and ai_intent.get('price'):
                intent['price'] = ai_intent['price']

        logger.debug(f"Extracted intent: {intent}")
        return intent

    def _resolve_intent_with_ai(self, question: str) -> Dict:
        """Use Gemini to extract full intent (Symbol, Action, Qty, Price) from text."""
        try:
            prompt = f"""Analyze this trading question and extract the intent.
            Question: "{question}"
            
            Return ONLY a valid JSON object with these keys:
            - symbol: Stock ticker (e.g., AAPL) or null
            - action: BUY, SELL, HOLD, or null
            - quantity: Number of shares (integer) or null
            - price: Price target (float) or null
            
            Example: {{"symbol": "GOOG", "action": "BUY", "quantity": 10, "price": 150.0}}"""
            
            response = self.gemini_model.generate_content(prompt)
            if response and response.text:
                # Use plain JSON parsing instead of _parse_response (which expects complex structure)
                text = response.text.strip()
                # Strip markdown code blocks if present
                if text.startswith('```'):
                    text = text.strip('`').strip()
                    if text.startswith('json'):
                        text = text[4:].strip()
                
                try:
                    result = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse AI intent JSON: {text[:100]}")
                    return {}
                
                # Validate symbol
                if result.get('symbol'):
                    sym = result['symbol'].upper()
                    # Basic validation: 1-5 letters
                    if re.match(r'^[A-Z]{1,5}$', sym) and sym != 'NONE':
                        result['symbol'] = sym
                    else:
                        result['symbol'] = None
                
                logger.info(f"AI resolved intent: {result}")
                return result
        except Exception as e:
            logger.warning(f"Failed to resolve intent with AI: {e}")
        
        return {}

    def _gather_context(self, symbol: str) -> Dict:
        """Gather all relevant context for a specific symbol."""
        context = {
            'symbol': symbol,
            'position': None,
            'market_data': None,
            'news': [],
            'recommendations': [],
            'portfolio_summary': None
        }
        
        # Check if we need to fetch live data first
        if self.market_analyst:
            try:
                # Check if we have recent data
                with get_connection(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT timestamp FROM market_data 
                        WHERE symbol = ? 
                        ORDER BY timestamp DESC LIMIT 1
                    """, (symbol.upper(),))
                    row = cursor.fetchone()
                    
                    need_fetch = True
                    if row:
                        last_update = datetime.fromisoformat(row[0])
                        # If data is less than 24 hours old (or market closed over weekend), use it
                        # But for chat, users usually want freshness. Let's say 24h cache.
                        if datetime.now() - last_update < timedelta(hours=24):
                            need_fetch = False
                    
                    if need_fetch:
                        logger.info(f"Fetching on-demand market data for {symbol}")
                        self.market_analyst.scan_symbols([symbol])
            except Exception as e:
                logger.error(f"Failed to fetch on-demand data: {e}")

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get current position
            cursor.execute("""
                SELECT h.quantity, h.cost_basis, h.current_value
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                WHERE h.symbol = ?
                ORDER BY p.import_timestamp DESC
                LIMIT 1
            """, (symbol.upper(),))
            position = cursor.fetchone()
            if position:
                context['position'] = {
                    'quantity': position[0],
                    'cost_basis': position[1],
                    'current_value': position[2]
                }
            
            # Get market data
            cursor.execute("""
                SELECT price, atr, sma_50, is_volatile, timestamp
                FROM market_data
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol.upper(),))
            market = cursor.fetchone()
            if market:
                context['market_data'] = {
                    'price': market[0],
                    'atr': market[1],
                    'sma_50': market[2],
                    'is_volatile': bool(market[3]),
                    'timestamp': market[4]
                }
            
            # Get recent news sentiment
            cursor.execute("""
                SELECT sentiment, confidence, key_reason, headline, timestamp
                FROM news_analysis
                WHERE symbol = ?
                AND datetime(timestamp) > datetime('now', '-72 hours')
                ORDER BY timestamp DESC
                LIMIT 5
            """, (symbol.upper(),))
            news = cursor.fetchall()
            context['news'] = [
                {
                    'sentiment': n[0],
                    'confidence': n[1],
                    'reason': n[2],
                    'headline': n[3],
                    'timestamp': n[4]
                }
                for n in news
            ]
            
            # Get past recommendations
            cursor.execute("""
                SELECT action, confidence, reasoning, timestamp
                FROM strategy_recommendations
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 3
            """, (symbol.upper(),))
            recs = cursor.fetchall()
            context['recommendations'] = [
                {
                    'action': r[0],
                    'confidence': r[1],
                    'reasoning': r[2],
                    'timestamp': r[3]
                }
                for r in recs
            ]
            
            # Get portfolio summary
            cursor.execute("""
                SELECT total_equity, cash_balance
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 1
            """)
            portfolio = cursor.fetchone()
            if portfolio:
                context['portfolio_summary'] = {
                    'total_equity': portfolio[0],
                    'cash_balance': portfolio[1]
                }

        
        return context
    
    def _gather_portfolio_context(self) -> Dict:
        """Gather general portfolio context when no specific symbol is mentioned."""
        context = {
            'symbol': None,
            'portfolio_summary': None,
            'holdings': [],
            'recommendations': []
        }
        
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get portfolio summary
            cursor.execute("""
                SELECT p.id, p.total_equity, p.cash_balance
                FROM portfolio_snapshot p
                ORDER BY p.import_timestamp DESC
                LIMIT 1
            """)
            portfolio = cursor.fetchone()
            if portfolio:
                snapshot_id = portfolio[0]
                context['portfolio_summary'] = {
                    'total_equity': portfolio[1],
                    'cash_balance': portfolio[2]
                }
                
                # Get all holdings
                cursor.execute("""
                    SELECT symbol, quantity, cost_basis, current_value
                    FROM holdings
                    WHERE snapshot_id = ?
                    AND quantity > 0
                """, (snapshot_id,))
                holdings = cursor.fetchall()
                context['holdings'] = [
                    {
                        'symbol': h[0],
                        'quantity': h[1],
                        'cost_basis': h[2],
                        'current_value': h[3]
                    }
                    for h in holdings
                ]
            
            # Get recent recommendations
            cursor.execute("""
                SELECT symbol, action, confidence, reasoning, timestamp
                FROM strategy_recommendations
                ORDER BY timestamp DESC
                LIMIT 10
            """)
            recs = cursor.fetchall()
            context['recommendations'] = [
                {
                    'symbol': r[0],
                    'action': r[1],
                    'confidence': r[2],
                    'reasoning': r[3],
                    'timestamp': r[4]
                }
                for r in recs
            ]

        
        return context
    
    def _build_prompt(self, question: str, intent: Dict, context: Dict) -> str:
        """Build the LLM prompt with Chain-of-Thought reasoning."""
        
        # Format position info
        position_str = "No current position"
        if context.get('position'):
            pos = context['position']
            qty = pos['quantity']
            cost = pos['cost_basis'] or 0
            value = pos['current_value'] or 0
            pl = value - (qty * cost) if cost else 0
            pl_pct = (pl / (qty * cost) * 100) if cost and qty else 0
            position_str = f"{qty:,.0f} shares, Cost: ${cost:.2f}, Value: ${value:,.2f}, P/L: ${pl:+,.2f} ({pl_pct:+.1f}%)"
        
        # Format market data
        market_str = "No recent market data available"
        if context.get('market_data'):
            md = context['market_data']
            price = md['price'] or 0
            atr = md['atr']
            sma = md['sma_50']
            market_str = f"Price: ${price:.2f}"
            if atr:
                market_str += f", ATR: ${atr:.2f}"
            if sma:
                trend = "above" if price > sma else "below"
                market_str += f", {trend} 50-day SMA (${sma:.2f})"
            if md['is_volatile']:
                market_str += " [HIGH VOLATILITY]"
        
        # Format news
        news_str = "No recent news"
        if context.get('news'):
            news_items = []
            for n in context['news'][:3]:
                news_items.append(f"- {n['sentiment'].upper()}: {n['reason']}")
            news_str = "\n".join(news_items)
        
        # Format past recommendations
        recs_str = "No previous recommendations"
        if context.get('recommendations'):
            rec_items = []
            for r in context['recommendations'][:3]:
                rec_items.append(f"- {r['action']} (confidence: {r['confidence']:.0%}): {r['reasoning'][:50]}...")
            recs_str = "\n".join(rec_items)
        
        # Format portfolio summary
        portfolio_str = "No portfolio data"
        if context.get('portfolio_summary'):
            ps = context['portfolio_summary']
            portfolio_str = f"Total Equity: ${ps['total_equity']:,.2f}, Cash: ${ps['cash_balance']:,.2f}"
        
        # Format holdings if available
        holdings_str = ""
        if context.get('holdings'):
            holdings_items = []
            total_equity = context.get('portfolio_summary', {}).get('total_equity', 0) or 0
            for h in context['holdings'][:10]:
                if total_equity > 0:
                    pct = (h['current_value'] / total_equity * 100)
                    holdings_items.append(f"- {h['symbol']}: {h['quantity']:.0f} shares, ${h['current_value']:,.2f} ({pct:.1f}%)")
                else:
                    holdings_items.append(f"- {h['symbol']}: {h['quantity']:.0f} shares, ${h['current_value']:,.2f}")
            holdings_str = "\nHoldings:\n" + "\n".join(holdings_items)
        
        # Build intent description
        intent_str = ""
        if intent.get('action'):
            intent_str = f"\nDetected Intent: {intent['action']}"
            if intent.get('quantity'):
                intent_str += f" {intent['quantity']} shares"
            if intent.get('symbol'):
                intent_str += f" of {intent['symbol']}"
            if intent.get('price'):
                intent_str += f" at ${intent['price']}"
        
        prompt = f"""You are a personal trading advisor. Answer the user's question about their portfolio or a specific trade.

USER QUESTION: {question}
{intent_str}

CONTEXT:
Portfolio: {portfolio_str}{holdings_str}

{"Position in " + context.get('symbol', 'N/A') + ": " + position_str if context.get('symbol') else ""}

Market Data: {market_str}

Recent News:
{news_str}

Previous Recommendations:
{recs_str}

INSTRUCTIONS:
1. Understand what the user is asking
2. Analyze the relevant data (position, market, news, past recommendations)
3. Consider risks and opportunities
4. Provide a clear, actionable recommendation

OUTPUT FORMAT (JSON only, no markdown, keep it concise):
{{
  "recommendation": "PROCEED" | "CAUTION" | "AVOID" | "MORE_INFO_NEEDED",
  "confidence": 0.0-1.0,
  "analysis": ["short point 1", "short point 2", "short point 3"],
  "reasoning": "Brief explanation in 30-50 words max"
}}

Respond ONLY with valid JSON. Keep analysis points SHORT (under 60 chars each)."""

        return prompt
    
    def _parse_response(self, response_text: str) -> Dict:
        """Parse the LLM response into structured data."""
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
        
        # Try to repair truncated JSON - extract what we can
        if start != -1:
            json_fragment = text[start:]
            # Try to extract recommendation
            rec_match = re.search(r'"recommendation"\s*:\s*"([^"]+)"', json_fragment)
            conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', json_fragment)
            
            if rec_match:
                # Extract analysis points that are complete
                analysis = []
                analysis_matches = re.findall(r'"([^"]{10,}?)"(?=\s*[,\]])', json_fragment)
                for a in analysis_matches[:5]:
                    if len(a) > 20 and not a.startswith('{'):
                        analysis.append(a)
                
                # Extract reasoning if present
                reason_match = re.search(r'"reasoning"\s*:\s*"([^"]+)', json_fragment)
                reasoning = reason_match.group(1) if reason_match else 'Response was truncated'
                
                return {
                    'recommendation': rec_match.group(1),
                    'confidence': float(conf_match.group(1)) if conf_match else 0.5,
                    'analysis': analysis if analysis else ['Response was truncated but recommendation extracted'],
                    'reasoning': reasoning
                }
        
        logger.warning(f"Failed to parse advisor response: {response_text[:200]}...")
        return {
            'recommendation': 'ERROR',
            'confidence': 0.0,
            'analysis': ['Failed to parse AI response'],
            'reasoning': response_text[:200]
        }
