"""
Risk Controller Agent

Enforces mathematical constraints and vetoes unsafe trades.
This is NOT an AI agent - pure deterministic Python logic.
No LLM hallucinations allowed in risk management.

Hard Constraints:
1. Cash Constraint: trade_cost ≤ available_cash
2. Position Size Limit: position_value ≤ 20% of portfolio_equity
3. Sector Exposure Cap: sector_total ≤ 40% of portfolio_equity
4. No Shorting: final_quantity ≥ 0
5. Volatility Filter: Reject if ATR > 10% of price
"""

import sqlite3
from datetime import datetime
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class RiskController:
    """Agent responsible for deterministic risk constraint enforcement."""
    
    def __init__(self, db_path: str, config: Optional[Dict] = None):
        """
        Initialize Risk Controller.
        
        Args:
            db_path: Path to SQLite database
            config: Optional risk configuration overrides
        """
        self.db_path = db_path
        
        # Default configuration
        self.MAX_POSITION_SIZE_PCT = 0.20  # 20% of equity
        self.MAX_SECTOR_EXPOSURE_PCT = 0.40  # 40% of equity
        self.MAX_VOLATILITY_PCT = 0.10  # 10% ATR relative to price
        self.RISK_PER_TRADE_PCT = 0.015  # 1.5% of equity at risk per trade
        self.STOP_LOSS_ATR_MULTIPLIER = 2.5  # 2.5x ATR for stops
        
        # Apply config overrides if provided
        if config:
            risk_config = config.get('risk', {})
            self.MAX_POSITION_SIZE_PCT = risk_config.get('max_position_size_pct', self.MAX_POSITION_SIZE_PCT)
            self.MAX_SECTOR_EXPOSURE_PCT = risk_config.get('max_sector_exposure_pct', self.MAX_SECTOR_EXPOSURE_PCT)
            self.MAX_VOLATILITY_PCT = risk_config.get('max_volatility_pct', self.MAX_VOLATILITY_PCT)
            self.RISK_PER_TRADE_PCT = risk_config.get('risk_per_trade_pct', self.RISK_PER_TRADE_PCT)
            self.STOP_LOSS_ATR_MULTIPLIER = risk_config.get('stop_loss_atr_multiplier', self.STOP_LOSS_ATR_MULTIPLIER)
    
    def validate_trade(self, recommendation: Dict) -> Dict:
        """
        Validate a trade recommendation against all risk rules.
        
        Args:
            recommendation: Dict with symbol, action, confidence, etc.
            
        Returns:
            Dict with:
            - approved: bool
            - reason: str
            - approved_shares: int (if approved)
            - approved_cost: float (if approved)
            - calculated_stop_loss: float (if applicable)
            - risk_per_trade: float
        """
        symbol = recommendation.get('symbol', 'UNKNOWN')
        action = recommendation.get('action', 'HOLD')
        
        if action == 'HOLD':
            return {'approved': True, 'reason': 'No action required'}
        
        # Get context
        context = self._get_risk_context(symbol)
        
        # Calculate proposed trade
        if action == 'BUY':
            result = self._validate_buy(symbol, recommendation, context)
        elif action == 'SELL':
            result = self._validate_sell(symbol, recommendation, context)
        else:
            result = {'approved': False, 'reason': f'Invalid action: {action}'}
        
        # Log decision
        self._log_decision(recommendation, result)
        
        return result
    
    def _validate_buy(self, symbol: str, rec: Dict, context: Dict) -> Dict:
        """Validate a BUY recommendation."""
        
        price = context.get('price', 0)
        atr = context.get('atr', 0)
        equity = context.get('portfolio_equity', 10000)
        cash = context.get('cash_balance', 0)
        current_position_value = context.get('current_position_value', 0)
        sector = context.get('sector', 'Unknown')
        sector_exposure = context.get('sector_exposure', 0)
        
        # Sanity check
        if price <= 0:
            return {
                'approved': False,
                'reason': f'Invalid price data for {symbol}'
            }
        
        # Calculate position size using Fixed Fractional method
        risk_amount = equity * self.RISK_PER_TRADE_PCT  # e.g., $10k * 1.5% = $150
        
        # Stop loss based on ATR or recommendation
        stop_loss = rec.get('stop_loss')
        if not stop_loss and atr:
            # Default: 2.5x ATR below entry
            stop_loss = price - (self.STOP_LOSS_ATR_MULTIPLIER * atr)
        elif not stop_loss:
            # Fallback: 5% below entry
            stop_loss = price * 0.95
        
        risk_per_share = price - stop_loss
        
        if risk_per_share <= 0:
            return {
                'approved': False,
                'reason': 'Stop loss is above entry price (invalid setup)'
            }
        
        # Calculate shares based on risk
        proposed_shares = int(risk_amount / risk_per_share)
        proposed_cost = proposed_shares * price
        
        # Check 1: Minimum viable order
        if proposed_shares < 1:
            return {
                'approved': False,
                'reason': f'Position size too small (risk allows less than 1 share)'
            }
        
        # Check 2: Sufficient cash?
        if proposed_cost > cash:
            # Adjust down to available cash
            adjusted_shares = int(cash / price)
            if adjusted_shares < 1:
                return {
                    'approved': False,
                    'reason': f'Insufficient cash. Need ${proposed_cost:.2f}, have ${cash:.2f}'
                }
            proposed_shares = adjusted_shares
            proposed_cost = proposed_shares * price
            logger.info(f"Reduced position to {proposed_shares} shares due to cash constraint")
        
        # Check 3: Position size limit
        new_position_value = current_position_value + proposed_cost
        max_position = equity * self.MAX_POSITION_SIZE_PCT
        
        if new_position_value > max_position:
            max_allowed_cost = max_position - current_position_value
            if max_allowed_cost < price:
                return {
                    'approved': False,
                    'reason': f'Position size limit. {symbol} would exceed {self.MAX_POSITION_SIZE_PCT*100:.0f}% of portfolio'
                }
            adjusted_shares = int(max_allowed_cost / price)
            if adjusted_shares < 1:
                return {
                    'approved': False,
                    'reason': f'Cannot add to position - already at {self.MAX_POSITION_SIZE_PCT*100:.0f}% limit'
                }
            proposed_shares = adjusted_shares
            proposed_cost = proposed_shares * price
            logger.info(f"Reduced position to {proposed_shares} shares due to position size limit")
        
        # Check 4: Sector exposure
        new_sector_exposure = sector_exposure + proposed_cost
        max_sector = equity * self.MAX_SECTOR_EXPOSURE_PCT
        
        if new_sector_exposure > max_sector:
            return {
                'approved': False,
                'reason': f'Sector limit. {sector} exposure would exceed {self.MAX_SECTOR_EXPOSURE_PCT*100:.0f}%'
            }
        
        # Check 5: Volatility filter
        if atr and price > 0:
            volatility_pct = atr / price
            if volatility_pct > self.MAX_VOLATILITY_PCT:
                return {
                    'approved': False,
                    'reason': f'Excessive volatility. ATR is {volatility_pct*100:.1f}% of price (max {self.MAX_VOLATILITY_PCT*100:.0f}%)'
                }
        
        # All checks passed!
        return {
            'approved': True,
            'reason': 'All risk checks passed',
            'approved_shares': proposed_shares,
            'approved_cost': proposed_cost,
            'calculated_stop_loss': stop_loss,
            'risk_per_trade': risk_amount,
            'position_pct': (new_position_value / equity) * 100
        }
    
    def _validate_sell(self, symbol: str, rec: Dict, context: Dict) -> Dict:
        """Validate a SELL recommendation."""
        
        current_quantity = context.get('current_quantity', 0)
        
        if current_quantity <= 0:
            return {
                'approved': False,
                'reason': 'Cannot sell. No position held.'
            }
        
        # For sells, we typically close the full position
        # (Partial sells could be implemented but add complexity)
        
        price = context.get('price', 0)
        sell_value = current_quantity * price if price else 0
        
        return {
            'approved': True,
            'reason': 'Sell approved',
            'approved_shares': int(current_quantity),
            'approved_value': sell_value
        }
    
    def _get_risk_context(self, symbol: str) -> Dict:
        """Fetch all data needed for risk calculations."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get market data
        cursor.execute("""
            SELECT price, atr
            FROM market_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        market = cursor.fetchone()
        
        # Get portfolio state
        cursor.execute("""
            SELECT total_equity, cash_balance
            FROM portfolio_snapshot
            ORDER BY import_timestamp DESC
            LIMIT 1
        """)
        portfolio = cursor.fetchone()
        
        # Get current position
        cursor.execute("""
            SELECT h.quantity, h.current_value
            FROM holdings h
            JOIN portfolio_snapshot p ON h.snapshot_id = p.id
            WHERE h.symbol = ?
            ORDER BY p.import_timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        position = cursor.fetchone()
        
        # Get sector from metadata
        cursor.execute("""
            SELECT sector FROM stock_metadata WHERE symbol = ?
        """, (symbol.upper(),))
        sector_row = cursor.fetchone()
        sector = sector_row[0] if sector_row else 'Unknown'
        
        # Get sector exposure (sum of all holdings in same sector)
        sector_exposure = 0
        if sector != 'Unknown':
            cursor.execute("""
                SELECT SUM(h.current_value)
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                JOIN stock_metadata s ON h.symbol = s.symbol
                WHERE s.sector = ?
                AND p.id = (SELECT id FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 1)
            """, (sector,))
            exp_row = cursor.fetchone()
            sector_exposure = exp_row[0] if exp_row and exp_row[0] else 0
        
        conn.close()
        
        return {
            'price': market[0] if market else 0,
            'atr': market[1] if market else 0,
            'portfolio_equity': portfolio[0] if portfolio else 10000,
            'cash_balance': portfolio[1] if portfolio else 10000,
            'current_quantity': position[0] if position else 0,
            'current_position_value': position[1] if position else 0,
            'sector': sector,
            'sector_exposure': sector_exposure
        }
    
    def _log_decision(self, recommendation: Dict, result: Dict):
        """Log all risk decisions for audit trail."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO risk_decisions
            (symbol, action, approved, reason, approved_shares, timestamp)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            recommendation.get('symbol'),
            recommendation.get('action'),
            1 if result['approved'] else 0,
            result['reason'],
            result.get('approved_shares')
        ))
        
        conn.commit()
        conn.close()
        
        status = "✅ APPROVED" if result['approved'] else "❌ VETOED"
        logger.info(f"Risk decision for {recommendation.get('symbol')}: {status} - {result['reason']}")
    
    def calculate_position_size(self, symbol: str, entry_price: float, 
                                 stop_loss_price: Optional[float] = None) -> Dict:
        """
        Calculate optimal position size for a new trade.
        
        Args:
            symbol: Stock ticker
            entry_price: Proposed entry price
            stop_loss_price: Optional stop loss price
            
        Returns:
            Dict with shares, cost, stop_loss, risk
        """
        context = self._get_risk_context(symbol)
        
        equity = context.get('portfolio_equity', 10000)
        cash = context.get('cash_balance', 10000)
        atr = context.get('atr', 0)
        
        # Risk amount
        risk_amount = equity * self.RISK_PER_TRADE_PCT
        
        # Stop loss
        if not stop_loss_price and atr:
            stop_loss_price = entry_price - (self.STOP_LOSS_ATR_MULTIPLIER * atr)
        elif not stop_loss_price:
            stop_loss_price = entry_price * 0.95
        
        risk_per_share = entry_price - stop_loss_price
        
        if risk_per_share <= 0:
            return {
                'error': 'Stop loss must be below entry price',
                'shares': 0,
                'cost': 0
            }
        
        shares = int(risk_amount / risk_per_share)
        cost = shares * entry_price
        
        # Cap by available cash
        if cost > cash:
            shares = int(cash / entry_price)
            cost = shares * entry_price
        
        # Cap by position size limit
        max_position = equity * self.MAX_POSITION_SIZE_PCT
        if cost > max_position:
            shares = int(max_position / entry_price)
            cost = shares * entry_price
        
        return {
            'shares': shares,
            'cost': cost,
            'stop_loss': stop_loss_price,
            'risk_amount': risk_amount,
            'risk_per_share': risk_per_share,
            'position_pct': (cost / equity * 100) if equity > 0 else 0
        }
    
    def get_risk_summary(self) -> Dict:
        """Get current portfolio risk metrics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest portfolio snapshot
        cursor.execute("""
            SELECT p.id, p.total_equity, p.cash_balance
            FROM portfolio_snapshot p
            ORDER BY p.import_timestamp DESC
            LIMIT 1
        """)
        snapshot = cursor.fetchone()
        
        if not snapshot:
            conn.close()
            return {'error': 'No portfolio data'}
        
        snapshot_id, equity, cash = snapshot
        
        # Get holdings with values
        cursor.execute("""
            SELECT h.symbol, h.current_value
            FROM holdings h
            WHERE h.snapshot_id = ?
        """, (snapshot_id,))
        holdings = cursor.fetchall()
        
        conn.close()
        
        # Calculate metrics
        invested = equity - cash
        cash_pct = (cash / equity * 100) if equity > 0 else 0
        
        largest_position = 0
        largest_symbol = None
        
        for symbol, value in holdings:
            pct = (value / equity * 100) if equity > 0 else 0
            if pct > largest_position:
                largest_position = pct
                largest_symbol = symbol
        
        return {
            'total_equity': equity,
            'cash_balance': cash,
            'invested_amount': invested,
            'cash_pct': cash_pct,
            'num_positions': len(holdings),
            'largest_position': largest_symbol,
            'largest_position_pct': largest_position,
            'max_position_limit': self.MAX_POSITION_SIZE_PCT * 100,
            'risk_per_trade': self.RISK_PER_TRADE_PCT * 100
        }
