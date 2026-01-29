"""
Cache Manager for Market Data

Provides TTL-based caching layer for market data to:
- Minimize API calls (respect rate limits)
- Ensure all agents see the same data snapshot
- Enable offline analysis if APIs are down
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages cached market data with TTL expiration."""
    
    def __init__(self, db_path: str, cache_ttl_seconds: int = 300):
        """
        Initialize Cache Manager.
        
        Args:
            db_path: Path to SQLite database
            cache_ttl_seconds: Cache time-to-live in seconds (default: 5 minutes)
        """
        self.db_path = db_path
        self.cache_ttl_seconds = cache_ttl_seconds
    
    def get_cached_price(self, symbol: str) -> Optional[float]:
        """
        Retrieve price from cache if fresh.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Cached price if fresh, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT price, timestamp
            FROM market_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        price, timestamp = row
        
        try:
            cache_time = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            return None
        
        # Check if cache is fresh
        if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl_seconds):
            logger.debug(f"Cache hit for {symbol}: ${price}")
            return price
        
        logger.debug(f"Cache expired for {symbol}")
        return None
    
    def get_cached_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full market data from cache if fresh.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dict with price, atr, sma_50, is_volatile if fresh, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT price, atr, sma_50, is_volatile, timestamp
            FROM market_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        price, atr, sma_50, is_volatile, timestamp = row
        
        try:
            cache_time = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            return None
        
        # Check if cache is fresh
        if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl_seconds):
            return {
                'price': price,
                'atr': atr,
                'sma_50': sma_50,
                'is_volatile': bool(is_volatile),
                'timestamp': timestamp
            }
        
        return None
    
    def cache_market_data(self, symbol: str, price: float, atr: Optional[float] = None,
                          sma_50: Optional[float] = None, is_volatile: bool = False,
                          source: str = 'Alpaca'):
        """
        Store market data in cache.
        
        Args:
            symbol: Stock ticker symbol
            price: Current price
            atr: Average True Range (optional)
            sma_50: 50-day Simple Moving Average (optional)
            is_volatile: Whether stock is currently volatile
            source: Data source name
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol.upper(),
            price,
            atr,
            sma_50,
            1 if is_volatile else 0,
            datetime.now().isoformat(),
            source
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Cached market data for {symbol}: ${price}")
    
    def cache_price(self, symbol: str, price: float, source: str = 'Alpaca'):
        """
        Store just price in cache (convenience method).
        
        Args:
            symbol: Stock ticker symbol
            price: Current price
            source: Data source name
        """
        self.cache_market_data(symbol, price, source=source)
    
    def invalidate_cache(self, symbol: Optional[str] = None):
        """
        Invalidate cache entries.
        
        Args:
            symbol: If provided, only invalidate for this symbol.
                   If None, invalidate all entries.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # We don't delete - just let TTL expire
        # But we can update timestamp to force expiration
        old_timestamp = (datetime.now() - timedelta(days=1)).isoformat()
        
        if symbol:
            cursor.execute("""
                UPDATE market_data
                SET timestamp = ?
                WHERE symbol = ?
            """, (old_timestamp, symbol.upper()))
            logger.info(f"Invalidated cache for {symbol}")
        else:
            cursor.execute("""
                UPDATE market_data
                SET timestamp = ?
            """, (old_timestamp,))
            logger.info("Invalidated all cache entries")
        
        conn.commit()
        conn.close()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM market_data")
        total_entries = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT symbol) FROM market_data
        """)
        unique_symbols = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp) FROM market_data
        """)
        oldest, newest = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_entries': total_entries,
            'unique_symbols': unique_symbols,
            'oldest_entry': oldest,
            'newest_entry': newest
        }
    
    def cleanup_old_entries(self, days_to_keep: int = 7):
        """
        Remove cache entries older than specified days.
        
        Args:
            days_to_keep: Number of days of data to retain
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        
        cursor.execute("""
            DELETE FROM market_data
            WHERE timestamp < ?
        """, (cutoff,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Cleaned up {deleted} old cache entries")
        return deleted
