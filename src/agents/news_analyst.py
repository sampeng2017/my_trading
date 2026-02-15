"""
News Analyst Agent

Parses financial news and extracts actionable intelligence.
Handles:
- Aggregating news from Finnhub
- AI-powered sentiment extraction using Gemini
- Urgency classification for notification routing
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from src.data.db_connection import get_connection
import json
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


class NewsAnalyst:
    """Agent responsible for news aggregation and sentiment analysis."""
    
    def __init__(self, db_path: str, finnhub_key: Optional[str] = None,
                 gemini_key: Optional[str] = None, config: Optional[Dict] = None):
        """
        Initialize News Analyst.
        
        Args:
            db_path: Path to SQLite database
            finnhub_key: Finnhub API key (optional)
            gemini_key: Google Gemini API key (optional)
            config: Configuration dict (optional)
        """
        self.db_path = db_path
        self.finnhub_key = finnhub_key
        self.config = config or {}
        self.gemini_model = None
        
        # AI configuration
        ai_config = self.config.get('ai', {})
        self.model_name = ai_config.get('model_sentiment', 'gemini-2.0-flash')
        self.temperature = ai_config.get('temperature', 0.1)
        
        # Configure Gemini if available
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini {self.model_name} initialized for news analysis")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
    
    def fetch_news(self, symbols: List[str], lookback_hours: int = 24) -> List[Dict]:
        """
        Fetch news for specific symbols from Finnhub.
        
        Args:
            symbols: List of stock ticker symbols
            lookback_hours: How many hours back to look for news
            
        Returns:
            List of news items with symbol, headline, summary, source, url, published
        """
        if not self.finnhub_key:
            logger.warning("Finnhub API key not configured")
            return []
        
        all_news = []
        from_date = self._get_from_date(lookback_hours)
        to_date = datetime.now().strftime('%Y-%m-%d')
        
        for symbol in symbols:
            try:
                url = "https://finnhub.io/api/v1/company-news"
                params = {
                    'symbol': symbol,
                    'token': self.finnhub_key,
                    'from': from_date,
                    'to': to_date
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    news_items = response.json()
                    
                    max_articles = self.config.get('limits', {}).get('max_news_articles', 5)
                    for item in news_items[:max_articles]:  # Limit per symbol
                        all_news.append({
                            'symbol': symbol,
                            'headline': item.get('headline'),
                            'summary': item.get('summary'),
                            'source': item.get('source'),
                            'url': item.get('url'),
                            'published': item.get('datetime')
                        })
                else:
                    logger.warning(f"Finnhub API error for {symbol}: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error fetching news for {symbol}: {e}")
        
        logger.info(f"Fetched {len(all_news)} news items for {len(symbols)} symbols")
        return all_news
    
    def analyze_sentiment(self, news_item: Dict) -> Dict:
        """
        Use Gemini to extract structured sentiment from news text.
        
        Args:
            news_item: Dict with headline, summary, symbol
            
        Returns:
            Analysis dict with sentiment, confidence, implied_action, urgency
        """
        if not self.gemini_model:
            return self._fallback_sentiment(news_item)
        
        prompt = self._build_sentiment_prompt(news_item)
        symbol = news_item.get('symbol', 'Unknown')
        
        def make_call():
            return self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=200
                )
            )
        
        response = call_with_retry(make_call, context=symbol)
        
        if response:
            result = self._parse_json_response(response.text)
            if result:
                result['symbol'] = symbol
                result['headline'] = news_item['headline']
                result['timestamp'] = datetime.now().isoformat()
                self._write_to_db(result)
                return result
        
        return self._fallback_sentiment(news_item)
    
    def analyze_batch(self, symbols: List[str]) -> List[Dict]:
        """
        Fetch and analyze news for multiple symbols.
        Groups articles by symbol and analyzes each group in a single Gemini call.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            List of sentiment analyses
        """
        news_items = self.fetch_news(symbols)
        if not news_items:
            return []

        analyses = []

        # Group articles by symbol for batched analysis
        from collections import defaultdict
        by_symbol = defaultdict(list)
        for item in news_items:
            by_symbol[item['symbol']].append(item)

        for i, (symbol, items) in enumerate(by_symbol.items()):
            if self.gemini_model and len(items) > 1:
                # Batch: analyze all articles for this symbol in one Gemini call
                batch_results = self._analyze_symbol_batch(items)
                analyses.extend(batch_results)
            else:
                # Single article or no AI: use per-article method
                for item in items:
                    analyses.append(self.analyze_sentiment(item))

        return analyses
    
    def _build_sentiment_prompt(self, news_item: Dict) -> str:
        """Build Chain-of-Thought prompt for sentiment extraction."""
        return f"""You are a financial news analyst. Analyze this news headline and summary.

Headline: {news_item.get('headline', 'N/A')}
Summary: {news_item.get('summary', 'N/A')}
Stock Ticker: {news_item.get('symbol', 'Unknown')}

Extract the following in JSON format ONLY (no preamble, no markdown):
{{
  "sentiment": "positive" | "negative" | "neutral",
  "confidence": 0.0-1.0,
  "implied_action": "BUY" | "SELL" | "HOLD",
  "key_reason": "brief explanation in 10 words or less",
  "urgency": "high" | "medium" | "low"
}}

Guidelines:
- sentiment: Overall tone of the news for the stock
- confidence: How certain the sentiment classification is
- implied_action: What a rational investor might consider
- key_reason: The main takeaway in very few words
- urgency: high = breaking/material news, medium = significant, low = routine

Output ONLY the JSON, no other text."""
    
    def _build_batch_sentiment_prompt(self, news_items: List[Dict]) -> str:
        """Build prompt to analyze multiple articles for the same symbol in one call."""
        symbol = news_items[0].get('symbol', 'Unknown')

        articles_text = ""
        for i, item in enumerate(news_items, 1):
            headline = item.get('headline', 'N/A')
            summary = (item.get('summary') or 'N/A')[:200]
            articles_text += f"\nArticle {i}:\n  Headline: {headline}\n  Summary: {summary}\n"

        return f"""You are a financial news analyst. Analyze these {len(news_items)} news articles for {symbol}.
{articles_text}
For EACH article, extract sentiment. Return a JSON array ONLY (no preamble, no markdown):
[
  {{
    "article_index": 1,
    "sentiment": "positive" | "negative" | "neutral",
    "confidence": 0.0-1.0,
    "implied_action": "BUY" | "SELL" | "HOLD",
    "key_reason": "brief explanation in 10 words or less",
    "urgency": "high" | "medium" | "low"
  }}
]

Guidelines:
- sentiment: Overall tone of each article for {symbol}
- confidence: How certain the sentiment classification is
- implied_action: What a rational investor might consider
- key_reason: The main takeaway in very few words
- urgency: high = breaking/material news, medium = significant, low = routine

Output ONLY the JSON array, no other text."""

    def _analyze_symbol_batch(self, news_items: List[Dict]) -> List[Dict]:
        """Analyze all articles for one symbol in a single Gemini call."""
        symbol = news_items[0].get('symbol', 'Unknown')
        prompt = self._build_batch_sentiment_prompt(news_items)

        def make_call():
            return self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=200 * len(news_items)
                )
            )

        response = call_with_retry(make_call, context=f"{symbol}_batch")

        if response:
            results = self._parse_batch_response(response.text, news_items)
            if results:
                return results

        # Fallback: return fallback sentiment for each article
        logger.warning(f"Batch sentiment failed for {symbol}, using fallback")
        return [self._fallback_sentiment(item) for item in news_items]

    def _parse_batch_response(self, response_text: str, news_items: List[Dict]) -> Optional[List[Dict]]:
        """Parse a JSON array response from batch sentiment analysis."""
        symbol = news_items[0].get('symbol', 'Unknown')

        # Try to extract JSON array
        text = response_text.strip()
        if text.startswith('```'):
            lines = text.split('\n', 1)
            text = lines[1] if len(lines) > 1 else text
            text = text.rsplit('```', 1)[0].strip()

        # Find array bounds
        start = text.find('[')
        end = text.rfind(']') + 1
        if start == -1 or end <= start:
            logger.warning(f"No JSON array found in batch response for {symbol}")
            return None

        try:
            parsed = json.loads(text[start:end])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse batch JSON for {symbol}")
            return None

        if not isinstance(parsed, list):
            return None

        # Filter to only valid dict entries
        parsed = [entry for entry in parsed if isinstance(entry, dict)]
        if not parsed:
            logger.warning(f"Batch response for {symbol} contained no valid entries")
            return None

        # Map results back to articles and write to DB
        results = []
        for i, item in enumerate(news_items):
            # Find matching result by article_index or position
            matched = None
            for entry in parsed:
                if entry.get('article_index') == i + 1:
                    matched = entry
                    break
            if not matched and i < len(parsed):
                matched = parsed[i]

            if matched:
                result = {
                    'symbol': symbol,
                    'headline': item.get('headline', ''),
                    'sentiment': matched.get('sentiment', 'neutral'),
                    'confidence': matched.get('confidence', 0.0),
                    'implied_action': matched.get('implied_action', 'HOLD'),
                    'key_reason': matched.get('key_reason', ''),
                    'urgency': matched.get('urgency', 'low'),
                    'timestamp': datetime.now().isoformat()
                }
                self._write_to_db(result)
                results.append(result)
            else:
                results.append(self._fallback_sentiment(item))

        return results

    def _parse_json_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from Gemini response, handling common issues."""
        try:
            # Try direct parse first
            return json.loads(response_text)
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

        # Try to find JSON object in text (Robust fallback)
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"Failed to parse JSON from response: {response_text[:100]}...")
        return None
    
    def _fallback_sentiment(self, news_item: Dict) -> Dict:
        """Fallback sentiment when AI is unavailable."""
        return {
            'symbol': news_item.get('symbol', 'Unknown'),
            'headline': news_item.get('headline', ''),
            'sentiment': 'neutral',
            'confidence': 0.0,
            'implied_action': 'HOLD',
            'key_reason': 'AI analysis unavailable',
            'urgency': 'low',
            'timestamp': datetime.now().isoformat()
        }
    
    def _write_to_db(self, analysis: Dict):
        """Store news analysis in database."""
        # Sanitize enum fields to match DB CHECK constraints
        sentiment = str(analysis.get('sentiment', 'neutral')).lower().strip()
        if sentiment not in ('positive', 'negative', 'neutral'):
            sentiment = 'neutral'
        action = str(analysis.get('implied_action', 'HOLD')).upper().strip()
        if action not in ('BUY', 'SELL', 'HOLD'):
            action = 'HOLD'
        urgency = str(analysis.get('urgency', 'low')).lower().strip()
        if urgency not in ('high', 'medium', 'low'):
            urgency = 'low'

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO news_analysis
                (symbol, headline, sentiment, confidence, implied_action, key_reason, urgency, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analysis.get('symbol'),
                analysis.get('headline'),
                sentiment,
                analysis.get('confidence'),
                action,
                analysis.get('key_reason'),
                urgency,
                analysis.get('timestamp')
            ))
            
            conn.commit()
        
        logger.debug(f"Wrote news analysis for {analysis.get('symbol')} to database")
    
    def _get_from_date(self, hours: int) -> str:
        """Get date string for lookback period."""
        from_dt = datetime.now() - timedelta(hours=hours)
        return from_dt.strftime('%Y-%m-%d')
    
    def get_recent_sentiment(self, symbol: str, limit: int = 5) -> List[Dict]:
        """
        Get recent sentiment analyses for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            limit: Maximum number of results
            
        Returns:
            List of recent sentiment analyses
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT sentiment, confidence, implied_action, key_reason, urgency, timestamp
                FROM news_analysis
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol.upper(), limit))
            
            rows = cursor.fetchall()
        
        return [
            {
                'sentiment': row[0],
                'confidence': row[1],
                'implied_action': row[2],
                'key_reason': row[3],
                'urgency': row[4],
                'timestamp': row[5]
            }
            for row in rows
        ]
    
    def get_high_urgency_news(self, hours: int = 4) -> List[Dict]:
        """Get all high-urgency news in recent period."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT symbol, headline, sentiment, confidence, implied_action, key_reason, timestamp
                FROM news_analysis
                WHERE urgency = 'high' AND timestamp > ?
                ORDER BY timestamp DESC
            """, (cutoff,))
            
            rows = cursor.fetchall()
        
        return [
            {
                'symbol': row[0],
                'headline': row[1],
                'sentiment': row[2],
                'confidence': row[3],
                'implied_action': row[4],
                'key_reason': row[5],
                'timestamp': row[6]
            }
            for row in rows
        ]
