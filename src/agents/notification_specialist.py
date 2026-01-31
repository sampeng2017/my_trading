"""
Notification Specialist Agent

Delivers alerts through appropriate channels.
Handles:
- iMessage for urgent/high priority alerts
- Email for summaries and batched notifications
- Quiet hours enforcement
- Daily summary generation
"""

import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time
from typing import Dict, List, Optional, Any
import logging
from src.data.db_connection import get_connection

logger = logging.getLogger(__name__)


class NotificationSpecialist:
    """Agent responsible for multi-channel notification delivery."""
    
    def __init__(self, db_path: str, config: Optional[Dict] = None):
        """
        Initialize Notification Specialist.
        
        Args:
            db_path: Path to SQLite database
            config: Configuration dict with notification settings
        """
        self.db_path = db_path
        self.config = config or {}
        
        # Quiet hours (no iMessage alerts)
        schedule = self.config.get('schedule', {})
        self.quiet_start = self._parse_time(schedule.get('quiet_hours_start', '21:00'))
        self.quiet_end = self._parse_time(schedule.get('quiet_hours_end', '06:00'))
        
        # Market hours
        self.market_open = self._parse_time(schedule.get('market_open', '06:30'))
        self.market_close = self._parse_time(schedule.get('market_close', '13:00'))
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        try:
            parts = time_str.split(':')
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return time(0, 0)
    
    def send_trade_alert(self, recommendation: Dict, risk_result: Dict):
        """
        Send a trade recommendation to the user.
        
        Args:
            recommendation: Dict with symbol, action, confidence, reasoning
            risk_result: Dict from RiskController with approval status
        """
        if not risk_result.get('approved'):
            # Trade was vetoed - log but don't alert (unless you want to notify of vetoes)
            logger.info(f"Trade for {recommendation.get('symbol')} vetoed: {risk_result.get('reason')}")
            return
        
        # Format message
        message = self._format_trade_message(recommendation, risk_result)
        
        # Check if we should send iMessage
        if self._should_send_imessage():
            success = self._send_imessage(message)
            if not success:
                # Fallback to email
                self._send_email(
                    subject=f"[Queued Alert] Trade: {recommendation.get('action')} {recommendation.get('symbol')}",
                    body=message
                )
        else:
            # Queue for email
            self._send_email(
                subject=f"Trade Alert: {recommendation.get('action')} {recommendation.get('symbol')}",
                body=message
            )
    
    def _format_trade_message(self, rec: Dict, risk: Dict) -> str:
        """Format a clean, actionable message."""
        action = rec.get('action', 'UNKNOWN')
        symbol = rec.get('symbol', 'UNKNOWN')
        confidence = rec.get('confidence', 0)
        reasoning = rec.get('reasoning', 'No reasoning provided')
        
        shares = risk.get('approved_shares', 0)
        cost = risk.get('approved_cost', 0)
        stop_loss = risk.get('calculated_stop_loss', 0)
        risk_amount = risk.get('risk_per_trade', 0)
        position_pct = risk.get('position_pct', 0)
        
        msg = f"""📊 TRADE ALERT - {action} {symbol}

💡 Recommendation: {action} {shares} shares @ market
📈 Confidence: {confidence:.0%}
🎯 Reasoning: {reasoning}

💰 Portfolio Impact:
   • Cost: ${cost:,.2f}
   • Position Size: {position_pct:.1f}% of portfolio
   • Stop Loss: ${stop_loss:.2f}
   
⚠️ Risk: ${risk_amount:.2f} (1.5% of portfolio)

Reply with action taken or 'SKIP' to dismiss.
System Time: {datetime.now().strftime('%I:%M %p PT')}"""

        return msg
    
    def send_batch_alerts(self, approved_trades: List[tuple]) -> bool:
        """
        Send all approved trades as a single combined message via iMessage AND email.
        
        Args:
            approved_trades: List of (recommendation, risk_result) tuples
            
        Returns:
            True if at least one channel succeeded
        """
        if not approved_trades:
            logger.info("No trades to send")
            return False
        
        # Build combined message
        message = self._format_batch_message(approved_trades)
        
        # Send via BOTH channels for reliability
        imessage_success = False
        email_success = False
        
        # Try iMessage
        if self._should_send_imessage():
            imessage_success = self._send_imessage(message)
        
        # Always send email for batch alerts (backup + record)
        subject = f"📊 Trading Alert: {len(approved_trades)} Recommendations"
        email_success = self._send_email(subject, message)
        
        if imessage_success:
            logger.info(f"Batch alert sent via iMessage ({len(approved_trades)} trades)")
        if email_success:
            logger.info(f"Batch alert sent via email ({len(approved_trades)} trades)")
        
        if not imessage_success and not email_success:
            logger.error("Failed to send batch alert via any channel")
            return False
            
        return True
    
    def _format_batch_message(self, approved_trades: List[tuple]) -> str:
        """Format multiple trades into a single readable message."""
        lines = [
            f"📊 TRADING RECOMMENDATIONS - {datetime.now().strftime('%b %d, %I:%M %p')}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        
        # Group by action type
        buys = [(rec, risk) for rec, risk in approved_trades if rec.get('action') == 'BUY']
        sells = [(rec, risk) for rec, risk in approved_trades if rec.get('action') == 'SELL']
        
        if sells:
            lines.append("🔴 SELL SIGNALS:")
            for rec, risk in sells:
                symbol = rec.get('symbol')
                shares = risk.get('approved_shares', 0)
                conf = rec.get('confidence', 0)
                reason = rec.get('reasoning', '')[:60]
                lines.append(f"  • {symbol}: {shares:,} shares ({conf:.0%})")
                lines.append(f"    └ {reason}...")
            lines.append("")
        
        if buys:
            lines.append("🟢 BUY SIGNALS:")
            for rec, risk in buys:
                symbol = rec.get('symbol')
                shares = risk.get('approved_shares', 0)
                cost = risk.get('approved_cost', 0)
                conf = rec.get('confidence', 0)
                reason = rec.get('reasoning', '')[:60]
                lines.append(f"  • {symbol}: {shares:,} shares @ ${cost:,.0f} ({conf:.0%})")
                lines.append(f"    └ {reason}...")
            lines.append("")
        
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Total: {len(sells)} sells, {len(buys)} buys",
            "Reply with actions taken or questions."
        ])
        
        return "\n".join(lines)
    
    def _send_imessage(self, message: str) -> bool:
        """
        Send via macOS Messages app using AppleScript.
        
        Returns:
            True if sent successfully, False otherwise
        """
        recipient = self.config.get('imessage', {}).get('recipient')
        
        if not recipient:
            logger.warning("iMessage recipient not configured")
            return False
        
        # Escape quotes in message
        escaped_msg = message.replace('\\', '\\\\').replace('"', '\\"')
        
        # AppleScript to send message
        script = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{recipient}" of targetService
            send "{escaped_msg}" to targetBuddy
        end tell
        '''
        
        try:
            subprocess.run(
                ['osascript', '-e', script],
                check=True,
                capture_output=True,
                timeout=10
            )
            self._log_notification('iMessage', message[:100], 'sent')
            logger.info(f"iMessage sent to {recipient}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"iMessage failed: {e}")
            self._log_notification('iMessage', message[:100], 'failed')
            return False
        except Exception as e:
            logger.error(f"iMessage error: {e}")
            self._log_notification('iMessage', message[:100], f'error: {str(e)[:50]}')
            return False
    
    def _send_email(self, subject: str, body: str, is_html: bool = False) -> bool:
        """
        Send via Gmail SMTP.
        
        Returns:
            True if sent successfully, False otherwise
        """
        email_config = self.config.get('email', {})
        smtp_user = email_config.get('username')
        smtp_pass = email_config.get('app_password')
        recipient = email_config.get('recipient')
        
        if not all([smtp_user, smtp_pass, recipient]):
            logger.warning("Email not fully configured")
            self._log_notification('email', subject, 'not_configured')
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = recipient
        
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        try:
            smtp_server = email_config.get('smtp_server', 'smtp.gmail.com')
            smtp_port = email_config.get('smtp_port', 465)
            
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            self._log_notification('email', subject, 'sent')
            logger.info(f"Email sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email failed: {e}")
            self._log_notification('email', subject, f'failed: {str(e)[:50]}')
            return False
    
    def _should_send_imessage(self) -> bool:
        """Check if it's appropriate to send iMessage."""
        now = datetime.now().time()
        
        # Check quiet hours (handles overnight range)
        if self.quiet_start > self.quiet_end:
            # Quiet hours span midnight
            if now >= self.quiet_start or now <= self.quiet_end:
                return False
        else:
            if self.quiet_start <= now <= self.quiet_end:
                return False
        
        # Optionally check market hours
        # Uncomment to restrict iMessage to market hours only:
        # if not (self.market_open <= now <= self.market_close):
        #     return False
        
        return True
    
    def _log_notification(self, channel: str, content: str, status: str):
        """Log all notifications for debugging."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO notification_log
                (channel, content, status, timestamp)
                VALUES (?, ?, ?, datetime('now'))
            """, (channel, content[:self.config.get('limits', {}).get('notification_truncation', 500)], status))
            
            conn.commit()
    
    def send_daily_summary(self):
        """Send end-of-day performance report via email."""
        # Gather data
        summary = self._generate_daily_summary()
        
        # Format as HTML email
        html = self._format_html_summary(summary)
        
        # Send
        self._send_email(
            subject=f"Daily Market Summary - {datetime.now().strftime('%B %d, %Y')}",
            body=html,
            is_html=True
        )
    
    def _generate_daily_summary(self) -> Dict:
        """Query database for daily performance metrics."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get today's recommendations (latest per symbol to avoid duplicates)
            cursor.execute("""
                SELECT symbol, action, confidence, reasoning
                FROM strategy_recommendations r
                WHERE DATE(timestamp) = DATE('now')
                AND r.id = (
                    SELECT id FROM strategy_recommendations r2 
                    WHERE r2.symbol = r.symbol 
                    AND DATE(r2.timestamp) = DATE('now')
                    ORDER BY r2.timestamp DESC 
                    LIMIT 1
                )
                ORDER BY timestamp DESC
            """)
            recommendations = cursor.fetchall()
            
            # Get portfolio value change
            cursor.execute("""
                SELECT total_equity, cash_balance
                FROM portfolio_snapshot
                ORDER BY import_timestamp DESC
                LIMIT 2
            """)
            equity_rows = cursor.fetchall()
            
            current_equity = equity_rows[0][0] if equity_rows else 10000
            previous_equity = equity_rows[1][0] if len(equity_rows) > 1 else current_equity
            daily_change = current_equity - previous_equity
            daily_change_pct = (daily_change / previous_equity) * 100 if previous_equity else 0
            
            # Get current holdings
            cursor.execute("""
                SELECT h.symbol, h.quantity, h.current_value
                FROM holdings h
                JOIN portfolio_snapshot p ON h.snapshot_id = p.id
                WHERE p.id = (SELECT id FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 1)
            """)
            holdings = cursor.fetchall()
        
        return {
            'recommendations': recommendations,
            'current_equity': current_equity,
            'daily_change': daily_change,
            'daily_change_pct': daily_change_pct,
            'holdings': holdings,
            'cash_balance': equity_rows[0][1] if equity_rows else 10000
        }
    
    def _format_html_summary(self, summary: Dict) -> str:
        """Create HTML-formatted email body."""
        change_class = 'positive' if summary['daily_change'] >= 0 else 'negative'
        
        # Build recommendations table
        rec_rows = ""
        if summary['recommendations']:
            for rec in summary['recommendations']:
                rec_rows += f"""
                <tr>
                  <td>{rec[0]}</td>
                  <td><strong>{rec[1]}</strong></td>
                  <td>{rec[2]:.0%}</td>
                  <td>{rec[3][:50]}...</td>
                </tr>
"""
        else:
            rec_rows = '<tr><td colspan="4">No recommendations generated today.</td></tr>'
        
        # Build holdings table
        holdings_rows = ""
        for h in summary['holdings']:
            holdings_rows += f"""
                <tr>
                  <td>{h[0]}</td>
                  <td>{h[1]:.0f}</td>
                  <td>${h[2]:,.2f}</td>
                </tr>
"""
        
        html = f"""
        <html>
          <head>
            <style>
              body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; }}
              .header {{ background-color: #1a73e8; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
              .metrics {{ margin: 20px; }}
              .positive {{ color: #0d9488; }}
              .negative {{ color: #dc2626; }}
              table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
              th, td {{ border: 1px solid #e5e7eb; padding: 10px; text-align: left; }}
              th {{ background-color: #f3f4f6; }}
              .container {{ max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; }}
            </style>
          </head>
          <body>
            <div class="container">
              <div class="header">
                <h1 style="margin: 0;">📈 Daily Trading Summary</h1>
                <p style="margin: 5px 0 0 0;">{datetime.now().strftime('%A, %B %d, %Y')}</p>
              </div>
              
              <div class="metrics">
                <h2>Portfolio Performance</h2>
                <table>
                  <tr><td>Current Equity</td><td><strong>${summary['current_equity']:,.2f}</strong></td></tr>
                  <tr><td>Daily Change</td><td class="{change_class}">
                    ${summary['daily_change']:+,.2f} ({summary['daily_change_pct']:+.2f}%)
                  </td></tr>
                  <tr><td>Cash Available</td><td>${summary['cash_balance']:,.2f}</td></tr>
                </table>
              </div>
              
              <div class="metrics">
                <h2>Current Holdings</h2>
                <table>
                  <tr><th>Symbol</th><th>Shares</th><th>Value</th></tr>
                  {holdings_rows}
                </table>
              </div>
              
              <div class="metrics">
                <h2>Today's Recommendations</h2>
                <table>
                  <tr><th>Symbol</th><th>Action</th><th>Confidence</th><th>Reasoning</th></tr>
                  {rec_rows}
                </table>
              </div>
              
              <div style="padding: 20px; background-color: #f3f4f6; text-align: center; border-radius: 0 0 8px 8px;">
                <small>Generated by Trading System • {datetime.now().strftime('%I:%M %p PT')}</small>
              </div>
            </div>
          </body>
        </html>
        """
        
        return html
    
    def send_critical_alert(self, message: str):
        """Send a critical alert immediately via all channels."""
        # Try iMessage regardless of quiet hours for critical alerts
        self._send_imessage(f"🚨 CRITICAL ALERT 🚨\n\n{message}")
        
        # Also send email
        self._send_email(
            subject="🚨 CRITICAL: Trading System Alert",
            body=message
        )
    
    def get_notification_history(self, limit: int = 20) -> List[Dict]:
        """Get recent notification history."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT channel, content, status, timestamp
                FROM notification_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
        
        return [
            {
                'channel': row[0],
                'content': row[1],
                'status': row[2],
                'timestamp': row[3]
            }
            for row in rows
        ]
