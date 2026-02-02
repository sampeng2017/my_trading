"""
Portfolio Accountant Agent

Parses Fidelity CSV exports and maintains portfolio state in the database.
Handles:
- Creating portfolio snapshots
- Extracting holdings and cash balances
- State diffing to infer trades
"""

import pandas as pd

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from src.data.db_connection import get_connection

logger = logging.getLogger(__name__)


class PortfolioAccountant:
    """Agent responsible for portfolio state management via CSV imports."""
    
    # Fidelity money market/cash symbols (also matches FCASH**)
    CASH_SYMBOLS = {'SPAXX', 'CORE', 'FDRXX', 'FCASH', 'FCASH**'}
    
    def __init__(self, db_path: str):
        """
        Initialize Portfolio Accountant.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure database and tables exist."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        
        # Check if tables exist
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='portfolio_snapshot'
            """)
            if not cursor.fetchone():
                logger.warning("Database tables not found. Run init_schema.sql first.")
    
    def import_fidelity_csv(self, csv_path: str) -> int:
        """
        Parse Fidelity CSV and update database.
        
        Args:
            csv_path: Path to Fidelity CSV export
            
        Returns:
            Snapshot ID of the created snapshot
        """
        logger.info(f"Importing Fidelity CSV: {csv_path}")

        # Read CSV with Fidelity-specific handling:
        # - utf-8-sig: handles BOM character from Windows exports
        # - on_bad_lines='skip': handles footer text and malformed rows
        # - index_col=False: prevents first column being used as DataFrame index
        df = pd.read_csv(csv_path, encoding='utf-8-sig', on_bad_lines='skip', index_col=False)

        # Normalize column names (handle variations)
        df.columns = df.columns.str.strip()

        # Filter out footer rows - keep only rows with valid Account Number
        if 'Account Number' in df.columns:
            # Valid account numbers start with letter+digits (e.g., X48681083)
            df = df[df['Account Number'].astype(str).str.match(r'^[A-Z]\d+', na=False)]
        
        # Validate required columns
        required_columns = {'Symbol', 'Current Value', 'Quantity'}
        missing = required_columns - set(df.columns)
        if missing:
            logger.error(f"CSV missing required columns: {missing}")
            raise ValueError(f"Invalid Fidelity CSV format. Missing: {missing}")
        
        # Create new snapshot
        snapshot_id = self._create_snapshot()
        
        total_holdings_value = 0.0
        cash_balance = 0.0
        
        for _, row in df.iterrows():
            symbol = str(row.get('Symbol', '')).strip().upper()
            
            if not symbol or symbol == 'NAN':
                continue
            


            # Handle "Pending activity" (usually negative debit for unsettled buys)
            # Fidelity CSV uses "Pending activity" in the Account Name or Symbol column depending on format
            # Based on user file: Symbol column contains "Pending activity"
            if 'PENDING ACTIVITY' in symbol.upper():
                pending_val = self._parse_currency(row.get('Current Value', 0))
                cash_balance += pending_val
                logger.debug(f"Pending activity detected: {pending_val:,.2f} (Adjusting cash)")
                continue

            # Skip invalid symbols (numeric IDs like CUSIP, restricted shares)
            if symbol.isdigit():
                logger.debug(f"Skipping numeric symbol (likely CUSIP): {symbol}")
                continue

            # Handle cash positions (Fidelity uses SPAXX for money market)
            # Also match symbols starting with known cash prefixes (e.g., FCASH**)
            is_cash = symbol in self.CASH_SYMBOLS or symbol.startswith('FCASH') or symbol.startswith('SPAXX')
            
            if is_cash:
                cash_value = self._parse_currency(row.get('Current Value', 0))
                cash_balance += cash_value
                logger.debug(f"Cash detected: {symbol} = ${cash_value:,.2f}")
            else:
                # Regular equity position
                quantity = self._parse_number(row.get('Quantity', 0))
                # Handle both column name variations
                cost_basis = self._parse_currency(
                    row.get('Cost Basis Per Share') or row.get('Average Cost Basis', 0)
                )
                current_value = self._parse_currency(row.get('Current Value', 0))
                
                if quantity > 0:
                    self._add_holding(
                        snapshot_id=snapshot_id,
                        symbol=symbol,
                        quantity=quantity,
                        cost_basis=cost_basis,
                        current_value=current_value
                    )
                    total_holdings_value += current_value
                    logger.debug(f"Holding: {symbol} x {quantity} = ${current_value:,.2f}")
        
        # Update cash in snapshot
        self._update_cash(snapshot_id, cash_balance)
        
        # Calculate and update total equity
        total_equity = total_holdings_value + cash_balance
        self._finalize_snapshot(snapshot_id)
        
        logger.info(f"Portfolio imported. Snapshot ID: {snapshot_id}, "
                   f"Equity: ${total_equity:,.2f}")
        
        # Run reconciliation to detect trades
        self._reconcile_with_previous()
        
        return snapshot_id
    
    def _parse_currency(self, value) -> float:
        """Parse currency string to float (handles $1,234.56 format)."""
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        # Remove $, commas, +/- signs, and whitespace
        cleaned = str(value).replace('$', '').replace(',', '').replace('+', '').strip()
        # Handle Fidelity's "--" for missing values
        if cleaned == '--' or cleaned == '':
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    
    def _parse_number(self, value) -> float:
        """Parse number string to float."""
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace(',', '').strip()
        # Handle Fidelity's "--" for missing values
        if cleaned == '--' or cleaned == '':
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    
    def _create_snapshot(self) -> int:
        """Create new snapshot entry and return its ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO portfolio_snapshot (import_timestamp, total_equity, cash_balance)
                VALUES (?, 0, 0)
            """, (datetime.now().isoformat(),))
            
            snapshot_id = cursor.lastrowid
            conn.commit()
            
        return snapshot_id
    
    def _add_holding(self, snapshot_id: int, symbol: str, quantity: float,
                     cost_basis: float, current_value: float):
        """Add holding to snapshot."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO holdings (snapshot_id, symbol, quantity, cost_basis, current_value)
                VALUES (?, ?, ?, ?, ?)
            """, (snapshot_id, symbol, quantity, cost_basis, current_value))
            
            conn.commit()
    
    def _update_cash(self, snapshot_id: int, cash_balance: float):
        """Update cash balance for snapshot."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE portfolio_snapshot
                SET cash_balance = ?
                WHERE id = ?
            """, (cash_balance, snapshot_id))
            
            conn.commit()
    
    def _finalize_snapshot(self, snapshot_id: int):
        """Calculate total equity for snapshot."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COALESCE(SUM(current_value), 0)
                FROM holdings 
                WHERE snapshot_id = ?
            """, (snapshot_id,))
            
            holdings_value = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT cash_balance 
                FROM portfolio_snapshot 
                WHERE id = ?
            """, (snapshot_id,))
            
            cash = cursor.fetchone()[0] or 0
            total_equity = holdings_value + cash
            
            cursor.execute("""
                UPDATE portfolio_snapshot
                SET total_equity = ?
                WHERE id = ?
            """, (total_equity, snapshot_id))
            
            conn.commit()
    
    def _reconcile_with_previous(self):
        """Compare new snapshot with previous to detect trades."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get last 2 snapshots
            cursor.execute("""
                SELECT id FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 2
            """)
            
            snapshots = cursor.fetchall()
            
            if len(snapshots) < 2:
                logger.info("No previous snapshot to compare.")
                return
            
            new_id, old_id = snapshots[0][0], snapshots[1][0]
            
            # Get holdings for both
            cursor.execute("""
                SELECT symbol, quantity, cost_basis
                FROM holdings
                WHERE snapshot_id = ?
            """, (old_id,))
            old_holdings = {row[0]: {'qty': row[1], 'basis': row[2]} for row in cursor.fetchall()}
            
            cursor.execute("""
                SELECT symbol, quantity, cost_basis
                FROM holdings
                WHERE snapshot_id = ?
            """, (new_id,))
            new_holdings = {row[0]: {'qty': row[1], 'basis': row[2]} for row in cursor.fetchall()}
        
        # Detect changes
        all_symbols = set(old_holdings.keys()) | set(new_holdings.keys())
        
        for symbol in all_symbols:
            old_qty = old_holdings.get(symbol, {}).get('qty', 0)
            new_qty = new_holdings.get(symbol, {}).get('qty', 0)
            
            delta = new_qty - old_qty
            
            if delta > 0:
                logger.info(f"📈 Detected BUY: {symbol} +{delta} shares")
                self._log_inferred_trade(symbol, 'BUY', delta, new_id)
            elif delta < 0:
                logger.info(f"📉 Detected SELL: {symbol} {delta} shares")
                self._log_inferred_trade(symbol, 'SELL', abs(delta), new_id)
    
    def _log_inferred_trade(self, symbol: str, action: str, quantity: float, snapshot_id: int):
        """Log inferred trade to audit trail."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trade_log (symbol, action, quantity, snapshot_id, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (symbol, action, quantity, snapshot_id, datetime.now().isoformat()))
            
            conn.commit()
    
    def get_latest_snapshot(self) -> Optional[Dict]:
        """Get the most recent portfolio snapshot."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, import_timestamp, total_equity, cash_balance
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            snapshot_id, timestamp, equity, cash = row
            
            # Get holdings
            cursor.execute("""
                SELECT symbol, quantity, cost_basis, current_value
                FROM holdings
                WHERE snapshot_id = ?
            """, (snapshot_id,))
            
            holdings = [
                {
                    'symbol': r[0],
                    'quantity': r[1],
                    'cost_basis': r[2],
                    'current_value': r[3]
                }
                for r in cursor.fetchall()
            ]
            
        return {
            'id': snapshot_id,
            'timestamp': timestamp,
            'total_equity': equity,
            'cash_balance': cash,
            'holdings': holdings
        }
    
    def get_holdings_symbols(self) -> List[str]:
        """Get list of symbols currently held in portfolio."""
        snapshot = self.get_latest_snapshot()
        if not snapshot:
            return []
        # Filter out invalid symbols (numeric IDs like CUSIP)
        return [h['symbol'] for h in snapshot['holdings'] if not h['symbol'].isdigit()]
    
    def get_portfolio_summary(self) -> Dict:
        """Get latest portfolio snapshot summary."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT total_equity, cash_balance, import_timestamp
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                return {"equity": 0, "cash": 0, "last_updated": None}
                
            return {
                "equity": row[0],
                "cash": row[1],
                "last_updated": row[2]
            }
            
    def get_current_holdings(self) -> List[Dict]:
        """Get current holdings."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT h.symbol, h.quantity, h.cost_basis, h.current_value
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                WHERE p.id = (SELECT id FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 1)
                ORDER BY h.current_value DESC
            """)
            
            return [
                {
                    "symbol": row[0],
                    "quantity": row[1],
                    "cost_basis": row[2],
                    "current_value": row[3],
                    "unrealized_pl": row[3] - (row[1] * row[2]) if row[1] > 0 else 0
                }
                for row in cursor.fetchall()
            ]
