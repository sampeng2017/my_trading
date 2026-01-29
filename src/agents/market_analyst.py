"""
Market Analyst Agent

Transforms raw market data into structured intelligence.
Handles:
- Real-time price fetching from Alpaca
- Technical indicator calculations (ATR, SMA)
- Volatility detection
- Market regime assessment
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3
import logging

logger = logging.getLogger(__name__)

# Try to import Alpaca - will fail gracefully if not installed
try:
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Market data features will be limited.")

# Try yfinance as fallback
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class MarketAnalyst:
    """Agent responsible for market data analysis and technical indicators."""
    
    def __init__(self, db_path: str, api_key: Optional[str] = None, 
                 api_secret: Optional[str] = None, config: Optional[Dict] = None):
        """
        Initialize Market Analyst.
        
        Args:
            db_path: Path to SQLite database
            api_key: Alpaca API key (optional, can use yfinance as fallback)
            api_secret: Alpaca API secret
            config: Configuration dict (optional)
        """
        self.db_path = db_path
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config or {}
        
        self.alpaca_client = None
        if ALPACA_AVAILABLE and api_key and api_secret:
            try:
                self.alpaca_client = StockHistoricalDataClient(api_key, api_secret)
                logger.info("Alpaca client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Alpaca client: {e}")
    
    def scan_symbols(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch current prices and calculate key metrics for multiple symbols.
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            Dict mapping symbol -> metrics dict
        """
        results = {}
        
        for symbol in symbols:
            try:
                metrics = self._analyze_symbol(symbol)
                if metrics:
                    results[symbol] = metrics
                    self._write_to_db(symbol, metrics)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
        
        return results
    
    def _analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Analyze a single symbol.
        
        Returns dict with price, atr, sma_50, is_volatile, timestamp
        """
        # Try Alpaca first, then yfinance
        if self.alpaca_client:
            df = self._fetch_alpaca_data(symbol)
        elif YFINANCE_AVAILABLE:
            df = self._fetch_yfinance_data(symbol)
        else:
            logger.error("No data source available")
            return None
        
        if df is None or df.empty:
            logger.warning(f"No data available for {symbol}")
            return None
        
        # Extract current price
        current_price = float(df['Close'].iloc[-1])
        
        # Calculate ATR for volatility
        atr = self._calculate_atr(df, period=14)
        
        # Calculate 50-day SMA
        sma_50 = None
        if len(df) >= 50:
            sma_50 = float(df['Close'].rolling(50).mean().iloc[-1])
        
        # Detect high volatility (ATR > 5% of price in recent period)
        is_volatile = False
        if atr and current_price > 0:
            is_volatile = (atr / current_price) > 0.05
        
        # Detect price spike (>2x ATR move in recent period)
        if atr and len(df) >= 15:
            recent_range = df['High'].iloc[-15:].max() - df['Low'].iloc[-15:].min()
            if recent_range > (2 * atr):
                is_volatile = True
        
        # Calculate 20-day average volume for liquidity check
        avg_volume = None
        if 'Volume' in df.columns and len(df) >= 20:
            avg_volume = int(df['Volume'].tail(20).mean())
        
        source = 'Alpaca' if self.alpaca_client else 'YFinance'
        
        return {
            'price': current_price,
            'atr': atr,
            'sma_50': sma_50,
            'avg_volume': avg_volume,
            'is_volatile': is_volatile,
            'source': source,
            'timestamp': datetime.now().isoformat()
        }
    
    def _fetch_alpaca_data(self, symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Fetch historical data from Alpaca."""
        if not self.alpaca_client:
            return None
        
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=datetime.now() - timedelta(days=days)
            )
            bars = self.alpaca_client.get_stock_bars(request)
            
            if not bars or symbol not in bars:
                return None
            
            df = bars[symbol].df
            # Rename columns to match yfinance format
            df.columns = [c.capitalize() for c in df.columns]
            return df
            
        except Exception as e:
            logger.error(f"Alpaca fetch error for {symbol}: {e}")
            return None
    
    def _fetch_yfinance_data(self, symbol: str, period: str = "60d") -> Optional[pd.DataFrame]:
        """Fetch historical data from Yahoo Finance."""
        if not YFINANCE_AVAILABLE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            
            if df.empty:
                return None
            
            return df
            
        except Exception as e:
            logger.error(f"yfinance fetch error for {symbol}: {e}")
            return None
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """
        Calculate Average True Range.
        
        ATR = Average of True Range over period
        True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        """
        if len(df) < period + 1:
            return None
        
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # Calculate True Range components
        high_low = high - low
        high_close = (high - close.shift()).abs()
        low_close = (low - close.shift()).abs()
        
        # True Range is max of the three
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # ATR is the rolling mean
        atr = true_range.rolling(period).mean().iloc[-1]
        
        return float(atr) if pd.notna(atr) else None
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """
        Calculate Relative Strength Index.
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        if len(df) < period + 1:
            return None
        
        delta = df['Close'].diff()
        
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
    
    def _write_to_db(self, symbol: str, metrics: Dict):
        """Persist market data to shared database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO market_data (symbol, price, atr, sma_50, volume, is_volatile, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol.upper(),
            metrics['price'],
            metrics.get('atr'),
            metrics.get('sma_50'),
            metrics.get('avg_volume'),
            1 if metrics.get('is_volatile') else 0,
            metrics['timestamp'],
            metrics.get('source', 'Unknown')
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Wrote market data for {symbol} to database")
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest cached price for a symbol.
        
        Falls back to live fetch if no cache exists.
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
        
        if row:
            price, timestamp = row
            # Check if cache is recent (within 5 minutes)
            try:
                cache_time = datetime.fromisoformat(timestamp)
                ttl = self.config.get('limits', {}).get('market_data_ttl_seconds', 300)
                if datetime.now() - cache_time < timedelta(seconds=ttl):
                    return price
            except:
                pass
        
        # Fetch fresh data
        metrics = self._analyze_symbol(symbol)
        if metrics:
            self._write_to_db(symbol, metrics)
            return metrics['price']
        
        return None
    
    def get_market_regime(self, symbol: str) -> str:
        """
        Assess the current market regime for a symbol.
        
        Returns: 'Trending Up', 'Trending Down', 'Ranging', or 'High Volatility'
        """
        if self.alpaca_client:
            df = self._fetch_alpaca_data(symbol, days=60)
        elif YFINANCE_AVAILABLE:
            df = self._fetch_yfinance_data(symbol, period="60d")
        else:
            return "Unknown"
        
        if df is None or len(df) < 50:
            return "Unknown"
        
        current_price = df['Close'].iloc[-1]
        sma_50 = df['Close'].rolling(50).mean().iloc[-1]
        sma_20 = df['Close'].rolling(20).mean().iloc[-1]
        
        atr = self._calculate_atr(df) or 0
        volatility_pct = atr / current_price if current_price > 0 else 0
        
        # High volatility override
        if volatility_pct > 0.05:
            return "High Volatility"
        
        # Trend detection
        if current_price > sma_50 and sma_20 > sma_50:
            return "Trending Up"
        elif current_price < sma_50 and sma_20 < sma_50:
            return "Trending Down"
        else:
            return "Ranging"
    
    def populate_metadata(self, symbols: List[str]):
        """
        Fetch and store sector/industry metadata for symbols.
        Crucial for RiskController sector exposure checks.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available for metadata population")
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        count = 0
        for symbol in symbols:
            try:
                # Check if already exists and recent
                cursor.execute("SELECT last_updated FROM stock_metadata WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                if row:
                    continue  # Skip existing
                
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                name = info.get('longName', symbol)
                avg_vol = info.get('averageVolume', 0)
                
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_metadata 
                    (symbol, name, sector, industry, avg_volume_20d, last_updated)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (symbol, name, sector, industry, avg_vol))
                
                count += 1
                
            except Exception as e:
                logger.error(f"Error fetching metadata for {symbol}: {e}")
        
        conn.commit()
        conn.close()
        logger.info(f"Populated metadata for {count} new symbols")
