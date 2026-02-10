"""
Stock Screener Agent

Discovers tradeable stocks dynamically using multiple data sources.
Primary: Alpaca Market Movers API
Backup: Alpha Vantage Top Gainers/Losers

Screening Criteria:
- Volume: Min 200k avg daily volume (from risk config)
- Price: $5-$500 range (avoid penny stocks and high-priced illiquids)
- Volatility: ATR < 10% of price (from risk config)
"""

import sqlite3
from src.data.db_connection import get_connection
import requests
import logging
import math
import re  # New import
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from src.utils.gemini_client import call_with_retry

logger = logging.getLogger(__name__)

# Try to import Alpaca
try:
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Screener will use Alpha Vantage only.")

# Try to import Google Generative AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. LLM ranking will be disabled.")


class StockScreener:
    """Agent that discovers tradeable stocks dynamically."""

    def __init__(self, db_path: str, alpaca_key: Optional[str] = None,
                 alpaca_secret: Optional[str] = None,
                 alpha_vantage_key: Optional[str] = None,
                 config: Optional[Dict] = None):
        """
        Initialize Stock Screener.

        Args:
            db_path: Path to SQLite database
            alpaca_key: Alpaca API key
            alpaca_secret: Alpaca API secret
            alpha_vantage_key: Alpha Vantage API key (backup)
            config: Configuration dict
        """
        self.db_path = db_path
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpha_vantage_key = alpha_vantage_key
        self.config = config or {}

        # Screening config
        screener_config = self.config.get('screener', {})
        self.cache_ttl = screener_config.get('cache_ttl_seconds', 3600)
        self.min_price = screener_config.get('min_price', 5.0)
        self.max_price = screener_config.get('max_price', 500.0)
        self.max_symbols = screener_config.get('max_screened_symbols', 10)

        # Risk config for filtering
        risk_config = self.config.get('risk', {})
        self.min_volume = risk_config.get('min_liquidity_volume', 200000)
        self.max_volatility = risk_config.get('max_volatility_pct', 0.10)

        # LLM re-ranking config
        self.use_llm_ranking = screener_config.get('use_llm_ranking', False)
        self.llm_candidate_pool = screener_config.get('llm_candidate_pool', 20)
        self.model_screening = screener_config.get('model_screening', 'gemini-2.5-pro')
        self.temperature_screening = screener_config.get('temperature_screening', 0.2)
        
        # Initialize Gemini for LLM ranking
        self.gemini_model = None
        if GEMINI_AVAILABLE and self.use_llm_ranking:
            gemini_key = self.config.get('api_keys', {}).get('gemini_api_key')
            if gemini_key:
                try:
                    genai.configure(api_key=gemini_key)
                    self.gemini_model = genai.GenerativeModel(self.model_screening)
                    logger.info(f"Gemini {self.model_screening} initialized for LLM screening")
                except Exception as e:
                    logger.warning(f"Failed to initialize Gemini for screening: {e}")

        # Initialize Alpaca client
        self.alpaca_client = None
        if ALPACA_AVAILABLE and alpaca_key and alpaca_secret:
            try:
                self.alpaca_client = StockHistoricalDataClient(alpaca_key, alpaca_secret)
                logger.info("Alpaca client initialized for screener")
            except Exception as e:
                logger.warning(f"Failed to initialize Alpaca client: {e}")

    def screen_stocks(self, max_symbols: Optional[int] = None) -> List[str]:
        """
        Main screening method. Returns list of tradeable symbols.

        Uses cached results if fresh, otherwise fetches new data.

        Args:
            max_symbols: Maximum symbols to return (default from config)

        Returns:
            List of stock symbols meeting screening criteria
        """
        max_symbols = max_symbols or self.max_symbols

        # Check cache first
        cached = self._get_cached_screening()
        if cached:
            logger.info(f"Using cached screening results: {len(cached)} symbols")
            return cached[:max_symbols]

        # Try Alpaca first
        candidates = []
        source = None

        if self.alpaca_client:
            try:
                candidates = self._fetch_alpaca_movers()
                source = 'Alpaca'
                logger.info(f"Alpaca returned {len(candidates)} candidates")
            except Exception as e:
                logger.warning(f"Alpaca screener failed: {e}")

        # Fallback to Alpha Vantage
        if not candidates and self.alpha_vantage_key:
            try:
                candidates = self._fetch_alpha_vantage_gainers()
                source = 'AlphaVantage'
                logger.info(f"Alpha Vantage returned {len(candidates)} candidates")
            except Exception as e:
                logger.warning(f"Alpha Vantage failed: {e}")

        # Fallback to stale cache (< 24 hours)
        if not candidates:
            stale = self._get_cached_screening(ttl_override=86400)
            if stale:
                logger.warning("Using stale cached screening (< 24h)")
                return stale[:max_symbols]

        # No data available
        if not candidates:
            logger.warning("All screeners failed, returning empty list")
            self._log_screener_run(source or 'None', 0, 0, "All sources failed")
            return []

        # Get static watchlist to avoid duplicates
        watchlist = set(self.config.get('watchlist', []))

        # Filter candidates
        filtered = self._apply_filters(candidates, watchlist)
        logger.info(f"After filtering: {len(filtered)} symbols")

        # Rank by tradability
        ranked = self._rank_candidates(filtered)

        # LLM re-ranking if enabled
        if self.use_llm_ranking and self.gemini_model and len(ranked) >= self.llm_candidate_pool:
            try:
                logger.info(f"Using LLM to re-rank top {self.llm_candidate_pool} candidates")
                pool = ranked[:self.llm_candidate_pool]
                # Get detailed data for LLM
                pool_data = [c for c in filtered if c['symbol'] in pool]
                final_ranked = self._llm_rerank_candidates(pool_data, max_symbols)
                logger.info(f"LLM re-ranking completed: {final_ranked}")
            except Exception as e:
                logger.warning(f"LLM re-ranking failed, using rule-based ranking: {e}")
                final_ranked = ranked[:max_symbols]
        else:
            final_ranked = ranked[:max_symbols]
            if self.use_llm_ranking and not self.gemini_model:
                logger.warning("LLM ranking enabled but Gemini not available")

        # Cache results
        self._cache_screening_results(final_ranked, source)
        self._log_screener_run(source, len(candidates), len(final_ranked), None)

        return final_ranked

    def _get_cached_screening(self, ttl_override: Optional[int] = None) -> Optional[List[str]]:
        """Check if fresh screening results exist in cache."""
        ttl = ttl_override or self.cache_ttl

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    SELECT symbol FROM screener_results
                    WHERE screening_timestamp > datetime('now', ?)
                    ORDER BY rank ASC
                """, (f'-{ttl} seconds',))

                results = cursor.fetchall()
                if results:
                    return [row[0] for row in results]
                return None

            except sqlite3.OperationalError:
                # Table doesn't exist yet
                return None

    def _fetch_alpaca_movers(self) -> List[Dict]:
        """
        Fetch most active stocks from Alpaca using REST API.
        The screener endpoints may not be in the Python SDK yet.
        """
        if not self.alpaca_key:
            return []

        candidates = []

        # Use Alpaca REST API for screener
        headers = {
            'APCA-API-KEY-ID': self.alpaca_key,
            'APCA-API-SECRET-KEY': self.alpaca_secret
        }

        # Try most actives endpoint
        try:
            url = "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives"
            params = {'by': 'volume', 'top': 50}
            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                for item in data.get('most_actives', []):
                    candidates.append({
                        'symbol': item.get('symbol'),
                        'volume': item.get('volume', 0),
                        'trade_count': item.get('trade_count', 0),
                        'source': 'Alpaca-MostActive'
                    })
        except Exception as e:
            logger.warning(f"Alpaca most-actives failed: {e}")

        # Try market movers (gainers/losers)
        try:
            url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"
            params = {'top': 20}
            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                for item in data.get('gainers', []) + data.get('losers', []):
                    # Avoid duplicates
                    if not any(c['symbol'] == item.get('symbol') for c in candidates):
                        candidates.append({
                            'symbol': item.get('symbol'),
                            'price': item.get('price', 0),
                            'change_pct': item.get('percent_change', 0),
                            'volume': item.get('volume', 0),
                            'source': 'Alpaca-Mover'
                        })
        except Exception as e:
            logger.warning(f"Alpaca movers failed: {e}")

        return candidates

    def _fetch_alpha_vantage_gainers(self) -> List[Dict]:
        """
        Fetch top gainers/losers from Alpha Vantage.
        Free tier: 25 calls/day
        """
        if not self.alpha_vantage_key:
            return []

        candidates = []

        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'TOP_GAINERS_LOSERS',
                'apikey': self.alpha_vantage_key
            }
            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()

                # Process top gainers
                for item in data.get('top_gainers', [])[:20]:
                    candidates.append({
                        'symbol': item.get('ticker'),
                        'price': float(item.get('price', 0)),
                        'change_pct': float(item.get('change_percentage', '0').replace('%', '')),
                        'volume': int(item.get('volume', 0)),
                        'source': 'AlphaVantage-Gainer'
                    })

                # Process top losers (also tradeable opportunities)
                for item in data.get('top_losers', [])[:10]:
                    candidates.append({
                        'symbol': item.get('ticker'),
                        'price': float(item.get('price', 0)),
                        'change_pct': float(item.get('change_percentage', '0').replace('%', '')),
                        'volume': int(item.get('volume', 0)),
                        'source': 'AlphaVantage-Loser'
                    })

                # Process most active
                for item in data.get('most_actively_traded', [])[:20]:
                    if not any(c['symbol'] == item.get('ticker') for c in candidates):
                        candidates.append({
                            'symbol': item.get('ticker'),
                            'price': float(item.get('price', 0)),
                            'change_pct': float(item.get('change_percentage', '0').replace('%', '')),
                            'volume': int(item.get('volume', 0)),
                            'source': 'AlphaVantage-Active'
                        })

        except Exception as e:
            logger.error(f"Alpha Vantage API error: {e}")

        return candidates

    def _enrich_missing_data(self, candidates: List[Dict]) -> List[Dict]:
        """
        Fetch prices and ATR for candidates missing data.
        
        Alpaca most-actives endpoint doesn't include price or volatility data,
        so we need to fetch it separately for proper filtering.
        """
        # Identify candidates needing enrichment
        needs_price = [c for c in candidates if not c.get('price')]
        needs_atr = [c for c in candidates if c.get('price') and not c.get('atr')]
        
        if not self.alpaca_client:
            return candidates
        
        # Enrich prices from quotes
        if needs_price:
            symbols = [c['symbol'] for c in needs_price if c.get('symbol')]
            if symbols:
                try:
                    request = StockLatestQuoteRequest(symbol_or_symbols=symbols)
                    quotes = self.alpaca_client.get_stock_latest_quote(request)
                    
                    for c in candidates:
                        if not c.get('price') and c['symbol'] in quotes:
                            q = quotes[c['symbol']]
                            # Handle bid-only, ask-only, or both
                            if q.bid_price and q.ask_price:
                                c['price'] = (q.bid_price + q.ask_price) / 2
                            elif q.ask_price:
                                c['price'] = q.ask_price
                            elif q.bid_price:
                                c['price'] = q.bid_price
                            if c.get('price'):
                                logger.debug(f"Enriched {c['symbol']} with price ${c['price']:.2f}")
                except Exception as e:
                    logger.warning(f"Failed to enrich prices: {e}")
        
        # For volatility filtering, we need ATR from historical data
        # Only fetch for candidates that passed price filter and lack ATR
        symbols_for_atr = [c['symbol'] for c in candidates 
                          if c.get('price') and not c.get('atr') and c.get('symbol')]
        
        if symbols_for_atr:
            self._enrich_atr(candidates, symbols_for_atr)
        
        return candidates
    
    def _enrich_atr(self, candidates: List[Dict], symbols: List[str]):
        """Fetch ATR data for symbols using historical bars."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        
        for symbol in symbols[:10]:  # Limit to avoid rate limits
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Day,
                    start=datetime.now() - timedelta(days=20)
                )
                bars = self.alpaca_client.get_stock_bars(request)
                
                if not bars:
                    continue
                
                # Extract DataFrame
                df = None
                if hasattr(bars, 'df') and not bars.df.empty:
                    df = bars.df
                    if hasattr(df.index, 'get_level_values'):
                        if symbol in df.index.get_level_values(0):
                            df = df.loc[symbol]
                elif symbol in bars:
                    df = bars[symbol].df
                
                if df is not None and len(df) >= 14:
                    # Calculate ATR
                    high = df['high'] if 'high' in df.columns else df['High']
                    low = df['low'] if 'low' in df.columns else df['Low']
                    close = df['close'] if 'close' in df.columns else df['Close']
                    
                    high_low = high - low
                    high_close = (high - close.shift()).abs()
                    low_close = (low - close.shift()).abs()
                    
                    import pandas as pd
                    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    atr = float(true_range.rolling(14).mean().iloc[-1])
                    
                    # Update candidate
                    for c in candidates:
                        if c['symbol'] == symbol:
                            c['atr'] = atr
                            logger.debug(f"Enriched {symbol} with ATR ${atr:.2f}")
                            break
                            
            except Exception as e:
                logger.debug(f"Failed to fetch ATR for {symbol}: {e}")

    def _apply_filters(self, candidates: List[Dict], watchlist: set) -> List[Dict]:
        """
        Apply screening criteria to filter candidates.

        Filters:
        - Not already in watchlist
        - Price in range
        - Volume above minimum
        - Valid symbol format
        """
        # Enrich candidates with missing price/ATR data (e.g., from Alpaca most-actives)
        candidates = self._enrich_missing_data(candidates)
        
        filtered = []

        for c in candidates:
            symbol = c.get('symbol', '')

            # Skip if already in watchlist
            if symbol in watchlist:
                continue

            # Skip invalid symbols (allow BRK.B, BF-B style tickers)
            if not symbol or len(symbol) > 6 or not re.match(r'^[A-Z]+[.\-]?[A-Z]*$', symbol):
                continue

            # Price filter - REQUIRE valid price (no bypass)
            price = c.get('price', 0)
            if not price or price < self.min_price or price > self.max_price:
                logger.debug(f"Filtered {symbol}: price ${price} invalid or out of range [{self.min_price}-{self.max_price}]")
                continue

            # Volatility filter (ATR-based if available)
            atr = c.get('atr', 0)
            if atr and price > 0:
                volatility_pct = atr / price
                if volatility_pct > self.max_volatility:
                    logger.debug(f"Filtered {symbol}: volatility {volatility_pct:.1%} exceeds max {self.max_volatility:.0%}")
                    continue

            # Volume filter
            volume = c.get('volume', 0)
            if volume and volume < self.min_volume:
                logger.debug(f"Filtered {symbol}: volume {volume} below minimum {self.min_volume}")
                continue

            filtered.append(c)

        return filtered

    def _rank_candidates(self, candidates: List[Dict]) -> List[str]:
        """
        Rank filtered candidates by tradability score.

        Score components:
        - Volume (40%): Higher volume = better liquidity
        - Momentum (30%): Larger price move = more opportunity
        - Recency (30%): Prefer recently active
        """
        scored = []

        for c in candidates:
            score = 0.0

            # Volume score (log-scaled)
            volume = c.get('volume', 0)
            if volume > 0:
                volume_ratio = volume / self.min_volume
                score += 0.4 * min(1.0, math.log10(max(1, volume_ratio)) / 2)

            # Momentum score (absolute % change)
            change_pct = abs(c.get('change_pct', 0))
            if change_pct > 0:
                score += 0.3 * min(1.0, change_pct / 10)

            # Recency score (from most-active sources)
            if 'Active' in c.get('source', ''):
                score += 0.3
            elif 'Mover' in c.get('source', ''):
                score += 0.2

            scored.append({
                'symbol': c['symbol'],
                'score': round(score, 3),
                'data': c
            })

        # Sort by score descending
        scored.sort(key=lambda x: x['score'], reverse=True)

        return [s['symbol'] for s in scored]

    def _llm_rerank_candidates(self, candidates: List[Dict], max_symbols: int) -> List[str]:
        """
        Use Gemini LLM to intelligently re-rank stock candidates.
        
        Args:
            candidates: List of candidate dicts with symbol, price, volume, change_pct
            max_symbols: Number of symbols to return
            
        Returns:
            List of top symbols after LLM re-ranking
        """
        if not self.gemini_model:
            logger.warning("Gemini model not available for re-ranking")
            return [c['symbol'] for c in candidates[:max_symbols]]
        
        import json  # Import at method level
        
        # Build prompt with candidate details
        candidate_list = ""
        for i, c in enumerate(candidates, 1):
            symbol = c.get('symbol', 'UNKNOWN')
            price = c.get('price', 0)
            volume = c.get('volume', 0)
            change = c.get('change_pct', 0)
            
            price_str = f"${price:.2f}" if price > 0 else "N/A"
            
            candidate_list += f"{i}. {symbol} - Price: {price_str}, Volume: {volume:,}, Change: {change:+.2f}%\n"
        
        prompt = f"""You are a stock screening analyst for swing trading. Re-rank these {len(candidates)} stocks by tradability.

Candidates:
{candidate_list}
Consider:
1. **Sector Rotation**: Which sectors have momentum in current market regime?
2. **Technical Setup**: Breakouts, bounces, or consolidations with potential
3. **Momentum Quality**: Sustainable moves vs exhaustion/parabolic
4. **Liquidity**: Higher volume = better execution
5. **Risk/Reward**: Clear entry/exit levels

Note: If Price is "N/A", it means data is missing but the stock has high volume. Do NOT disqualify based on missing price. Focus on volume and ticker reputation.

Return JSON with top {max_symbols} symbols ranked by tradability:
{{
  "rankings": [
    {{"symbol": "AAPL", "score": 95, "reason": "Brief reason (1 sentence)"}},
    ...
  ]
}}

Respond ONLY with valid JSON, no markdown formatting."""
        
        try:
            # Call Gemini with low temperature for consistency
            # Disable safety filters for financial analysis (not giving advice, just screening)
            def _make_llm_call():
                return self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=self.temperature_screening,
                        max_output_tokens=4000
                    ),
                    safety_settings={
                        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE"
                    }
                )

            response = call_with_retry(_make_llm_call, context="screener_rerank")

            if not response:
                logger.warning("LLM re-ranking failed after retries, using rule-based order")
                return [c['symbol'] for c in candidates[:max_symbols]]

            # Check if response has text (may be blocked by safety filters)
            if not response.text:
                logger.warning(f"LLM response blocked (finish_reason: {response.candidates[0].finish_reason if response.candidates else 'unknown'})")
                return [c['symbol'] for c in candidates[:max_symbols]]
            
            # Parse JSON response
            response_text = response.text.strip()
            
            # Log raw response for debugging
            logger.debug(f"Raw LLM response: {response_text[:500]}")
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('\n', 1)[1]
                response_text = response_text.rsplit('```', 1)[0]
            
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback: Try regex to extract rankings array
                logger.warning("JSON parse failed, trying regex fallback")
                
                # Ultimate fallback: Just extract symbols in appearing order!
                # Since the LLM is asked to rank them, the order of appearance is the rank.
                matches = re.findall(r'"symbol":\s*"([^"]+)"', response_text)
                
                if matches:
                    logger.info(f"Extracted {len(matches)} symbols via regex fallback")
                    # Reconstruct minimal valid data structure
                    rankings = [{"symbol": s, "reason": "Extracted via regex"} for s in matches]
                    data = {"rankings": rankings}
                else:
                    raise  # Re-raise if absolutely nothing found
            
            rankings = data.get('rankings', [])
            
            # Extract symbols in ranked order
            ranked_symbols = [r['symbol'] for r in rankings if 'symbol' in r]
            
            # Log reasoning for top stocks
            for i, r in enumerate(rankings[:3], 1):
                logger.info(f"LLM Rank #{i}: {r.get('symbol')} - {r.get('reason', 'No reason')}")
            
            if len(ranked_symbols) >= max_symbols:
                return ranked_symbols[:max_symbols]
            else:
                logger.warning(f"LLM returned only {len(ranked_symbols)} symbols, expected {max_symbols}")
                # Fill remaining with rule-based ranking
                remaining = [c['symbol'] for c in candidates if c['symbol'] not in ranked_symbols]
                return (ranked_symbols + remaining)[:max_symbols]
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            if 'response_text' in locals():
                logger.debug(f"Response text: {response_text[:500]}")
            # Fallback to rule-based
            return [c['symbol'] for c in candidates[:max_symbols]]
        except AttributeError as e:
            logger.error(f"LLM response missing expected attributes: {e}")
            # Fallback to rule-based
            return [c['symbol'] for c in candidates[:max_symbols]]
        except Exception as e:
            logger.error(f"LLM re-ranking error: {e}")
            # Fallback to rule-based
            return [c['symbol'] for c in candidates[:max_symbols]]

    def _cache_screening_results(self, symbols: List[str], source: str):
        """Store screening results in database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            try:
                # Clear old results
                cursor.execute("DELETE FROM screener_results")

                # Insert new results
                for rank, symbol in enumerate(symbols, 1):
                    cursor.execute("""
                        INSERT INTO screener_results (symbol, source, rank, screening_timestamp)
                        VALUES (?, ?, ?, datetime('now'))
                    """, (symbol, source, rank))

                conn.commit()
                logger.info(f"Cached {len(symbols)} screening results from {source}")

            except sqlite3.OperationalError as e:
                logger.warning(f"Could not cache results (table may not exist): {e}")

    def _log_screener_run(self, source: str, found: int, filtered: int, error: Optional[str]):
        """Log screener run for auditing."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO screener_runs
                    (run_timestamp, source, symbols_found, symbols_after_filter, error)
                    VALUES (datetime('now'), ?, ?, ?, ?)
                """, (source, found, filtered, error))
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Table doesn't exist yet

    def get_screening_stats(self) -> Dict:
        """Get statistics about recent screenings."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            stats = {
                'last_run': None,
                'total_runs_today': 0,
                'avg_symbols_found': 0,
                'sources_used': []
            }

            try:
                # Last run
                cursor.execute("""
                    SELECT run_timestamp, source, symbols_found, symbols_after_filter
                    FROM screener_runs
                    ORDER BY run_timestamp DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    stats['last_run'] = {
                        'timestamp': row[0],
                        'source': row[1],
                        'found': row[2],
                        'filtered': row[3]
                    }

                # Today's stats
                cursor.execute("""
                    SELECT COUNT(*), AVG(symbols_found), GROUP_CONCAT(DISTINCT source)
                    FROM screener_runs
                    WHERE DATE(run_timestamp) = DATE('now')
                """)
                row = cursor.fetchone()
                if row:
                    stats['total_runs_today'] = row[0] or 0
                    stats['avg_symbols_found'] = round(row[1] or 0, 1)
                    stats['sources_used'] = (row[2] or '').split(',')

            except sqlite3.OperationalError:
                pass

        return stats
