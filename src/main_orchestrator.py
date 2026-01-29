#!/usr/bin/env python3
"""
Main Orchestrator for Trading System

Entry point that coordinates all agents based on time of day.
Designed to be run by launchd on a schedule.

Modes:
- Pre-market (6:00-6:30 AM): Scan watchlist, prepare for open
- Market hours (6:30 AM - 1:00 PM): Active monitoring and recommendations
- Post-market (1:00-2:00 PM): Daily summary generation
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import logging
import argparse

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytz

from utils.config import load_config, get_db_path
from agents.portfolio_accountant import PortfolioAccountant
from agents.market_analyst import MarketAnalyst
from agents.news_analyst import NewsAnalyst
from agents.strategy_planner import StrategyPlanner
from agents.risk_controller import RiskController
from agents.notification_specialist import NotificationSpecialist

# Setup logging
def setup_logging(log_path: str = None):
    """Configure logging."""
    handlers = [logging.StreamHandler()]
    
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Main coordinator for all trading agents."""
    
    def __init__(self, config: dict = None):
        """
        Initialize orchestrator with all agents.
        
        Args:
            config: Configuration dict (loads from file if not provided)
        """
        self.config = config or load_config()
        self.db_path = get_db_path(self.config)
        
        # Initialize agents
        api_keys = self.config.get('api_keys', {})
        
        self.portfolio = PortfolioAccountant(self.db_path)
        
        self.market = MarketAnalyst(
            self.db_path,
            api_key=api_keys.get('alpaca_api_key'),
            api_secret=api_keys.get('alpaca_secret_key'),
            config=self.config
        )
        
        self.news = NewsAnalyst(
            self.db_path,
            finnhub_key=api_keys.get('finnhub_api_key'),
            gemini_key=api_keys.get('gemini_api_key'),
            config=self.config
        )
        
        self.strategy = StrategyPlanner(
            self.db_path,
            gemini_key=api_keys.get('gemini_api_key')
        )
        
        self.risk = RiskController(self.db_path, self.config)
        
        self.notifier = NotificationSpecialist(self.db_path, self.config)
        
        # Get timezone
        tz_name = self.config.get('schedule', {}).get('timezone', 'America/Los_Angeles')
        self.tz = pytz.timezone(tz_name)
    
    def get_current_mode(self) -> str:
        """Determine current operating mode based on time."""
        now = datetime.now(self.tz)
        hour = now.hour
        minute = now.minute
        
        if 6 <= hour < 7 and minute < 30:
            return 'premarket'
        elif (hour == 6 and minute >= 30) or (7 <= hour < 13):
            return 'market'
        elif 13 <= hour < 14:
            return 'postmarket'
        else:
            return 'closed'
    
    def run(self, mode: str = None):
        """
        Run orchestration based on mode.
        
        Args:
            mode: Operating mode (auto-detects if not specified)
        """
        mode = mode or self.get_current_mode()
        now = datetime.now(self.tz)
        
        logger.info(f"=" * 60)
        logger.info(f"Trading System Orchestrator - {now.strftime('%Y-%m-%d %I:%M %p %Z')}")
        logger.info(f"Mode: {mode.upper()}")
        logger.info(f"=" * 60)
        
        if mode == 'premarket':
            self.run_premarket()
        elif mode == 'market':
            self.run_market_hours()
        elif mode == 'postmarket':
            self.run_postmarket()
        else:
            logger.info(f"Outside market hours ({now.strftime('%I:%M %p')}). No action taken.")
    
    def run_premarket(self):
        """Pre-market analysis routine."""
        logger.info("📅 Running pre-market scan...")
        
        # Get symbols to monitor
        symbols = self._get_monitoring_symbols()
        logger.info(f"Monitoring {len(symbols)} symbols: {', '.join(symbols)}")
        
        # Ensure metadata is populated (sectors/industries for risk)
        logger.info("Populating stock metadata...")
        self.market.populate_metadata(symbols)
        
        # Fetch market data
        logger.info("Fetching market data...")
        market_data = self.market.scan_symbols(symbols)
        logger.info(f"Market data fetched for {len(market_data)} symbols")
        
        # Fetch and analyze news
        logger.info("Analyzing news...")
        news_analyses = self.news.analyze_batch(symbols)
        logger.info(f"Analyzed {len(news_analyses)} news items")
        
        # Check for high-urgency news
        urgent_news = self.news.get_high_urgency_news(hours=12)
        if urgent_news:
            logger.warning(f"⚠️ Found {len(urgent_news)} high-urgency news items")
            for news in urgent_news:
                logger.warning(f"  - {news['symbol']}: {news['headline'][:50]}...")
        
        logger.info("✅ Pre-market scan complete")
    
    def run_market_hours(self):
        """Active market hours routine."""
        logger.info("📈 Running market hours analysis...")
        
        # Get symbols
        symbols = self._get_monitoring_symbols()
        
        # Update market data
        logger.info("Updating market data...")
        market_data = self.market.scan_symbols(symbols)
        
        # Check for recent news
        news_analyses = self.news.analyze_batch(symbols)
        
        # Generate recommendations
        logger.info("Generating recommendations...")
        recommendations = []
        
        for symbol in symbols:
            rec = self.strategy.generate_recommendation(symbol)
            if rec and rec.get('action') != 'HOLD':
                recommendations.append(rec)
                logger.info(f"  {symbol}: {rec.get('action')} (confidence: {rec.get('confidence', 0):.0%})")
        
        # Validate through risk controller
        approved_trades = []
        
        for rec in recommendations:
            result = self.risk.validate_trade(rec)
            
            if result['approved']:
                approved_trades.append((rec, result))
                logger.info(f"  ✅ {rec['symbol']} approved: {result.get('approved_shares', 0)} shares")
            else:
                logger.info(f"  ❌ {rec['symbol']} vetoed: {result['reason']}")
        
        # Send notifications for approved trades
        for rec, result in approved_trades:
            self.notifier.send_trade_alert(rec, result)
        
        logger.info(f"✅ Market hours analysis complete. {len(approved_trades)} trade alerts sent.")
    
    def run_postmarket(self):
        """Post-market summary routine."""
        logger.info("📊 Running post-market summary...")
        
        # Generate and send daily summary
        self.notifier.send_daily_summary()
        
        # Log portfolio summary
        snapshot = self.portfolio.get_latest_snapshot()
        if snapshot:
            logger.info(f"Portfolio Equity: ${snapshot['total_equity']:,.2f}")
            logger.info(f"Cash Balance: ${snapshot['cash_balance']:,.2f}")
            logger.info(f"Holdings: {len(snapshot['holdings'])}")
        
        # Log risk summary
        risk_summary = self.risk.get_risk_summary()
        if 'error' not in risk_summary:
            logger.info(f"Largest Position: {risk_summary.get('largest_position')} "
                       f"({risk_summary.get('largest_position_pct', 0):.1f}%)")
        
        logger.info("✅ Post-market summary complete")
    
    def _get_monitoring_symbols(self) -> list:
        """Get list of symbols to monitor."""
        # Start with watchlist from config
        symbols = set(self.config.get('watchlist', []))
        
        # Add current portfolio holdings
        holdings = self.portfolio.get_holdings_symbols()
        symbols.update(holdings)
        
        return list(symbols)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Trading System Orchestrator')
    parser.add_argument('--mode', choices=['premarket', 'market', 'postmarket', 'auto'],
                       default='auto', help='Operating mode (default: auto-detect)')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--log', help='Path to log file')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log)
    
    # Load config
    config = None
    if args.config:
        config = load_config(args.config)
    
    # Run orchestrator
    orchestrator = TradingOrchestrator(config)
    
    mode = None if args.mode == 'auto' else args.mode
    orchestrator.run(mode)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
