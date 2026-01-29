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
import requests
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Try to import Alpaca
try:
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Screener will use Alpha Vantage only.")


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

        # Cache results
        self._cache_screening_results(ranked, source)
        self._log_screener_run(source, len(candidates), len(ranked), None)

        return ranked[:max_symbols]

    def _get_cached_screening(self, ttl_override: Optional[int] = None) -> Optional[List[str]]:
        """Check if fresh screening results exist in cache."""
        ttl = ttl_override or self.cache_ttl

        conn = sqlite3.connect(self.db_path)
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
        finally:
            conn.close()

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

    def _apply_filters(self, candidates: List[Dict], watchlist: set) -> List[Dict]:
        """
        Apply screening criteria to filter candidates.

        Filters:
        - Not already in watchlist
        - Price in range
        - Volume above minimum
        - Valid symbol format
        """
        filtered = []

        for c in candidates:
            symbol = c.get('symbol', '')

            # Skip if already in watchlist
            if symbol in watchlist:
                continue

            # Skip invalid symbols (must be 1-5 uppercase letters)
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                continue

            # Price filter
            price = c.get('price', 0)
            if price and (price < self.min_price or price > self.max_price):
                logger.debug(f"Filtered {symbol}: price ${price} out of range")
                continue

            # Volume filter
            volume = c.get('volume', 0)
            if volume and volume < self.min_volume:
                logger.debug(f"Filtered {symbol}: volume {volume} below minimum")
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

    def _cache_screening_results(self, symbols: List[str], source: str):
        """Store screening results in database."""
        conn = sqlite3.connect(self.db_path)
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
        finally:
            conn.close()

    def _log_screener_run(self, source: str, found: int, filtered: int, error: Optional[str]):
        """Log screener run for auditing."""
        conn = sqlite3.connect(self.db_path)
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
        finally:
            conn.close()

    def get_screening_stats(self) -> Dict:
        """Get statistics about recent screenings."""
        conn = sqlite3.connect(self.db_path)
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
        finally:
            conn.close()

        return stats
