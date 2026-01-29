# Automated Stock Trading Intelligence System
## A Pragmatic Architecture for macOS

**Version:** 1.0  
**Target Platform:** macOS (Apple Silicon or Intel)  
**Capital:** $10,000 USD  
**Brokerage:** Fidelity Individual Account  
**Risk Profile:** Medium to Moderately High  
**Trading Style:** Swing/Position Trading (days to weeks)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Agent Specifications](#3-agent-specifications)
4. [Data Layer](#4-data-layer)
5. [Risk Management Engine](#5-risk-management-engine)
6. [AI Integration Strategy](#6-ai-integration-strategy)
7. [macOS Automation](#7-macos-automation)
8. [Portfolio Management](#8-portfolio-management)
9. [User Experience & Notifications](#9-user-experience--notifications)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Database Schemas](#11-database-schemas)
12. [Configuration & Deployment](#12-configuration--deployment)
13. [Evaluation & Continuous Improvement](#13-evaluation--continuous-improvement)

---

## 1. Executive Summary

### 1.1 System Philosophy

This system implements a **Human-in-the-Loop (HITL)** automated trading intelligence platform that operates locally on macOS. It functions as a digital analyst that:

- **Perceives:** Continuously monitors market data and news
- **Analyzes:** Synthesizes information using AI reasoning
- **Recommends:** Generates actionable trade suggestions
- **Respects:** Defers all execution decisions to you (the human)

**Core Principle:** *Deterministic Safety in a Probabilistic World*

While AI models provide probabilistic reasoning for market interpretation, the system enforces deterministic mathematical constraints for risk management and data integrity.

### 1.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Local Execution** | Privacy, no dependency on cloud infrastructure, full control |
| **Gemini API (Paid Tier)** | Privacy guarantee (no training on your data), massive context window (1M+ tokens), cost-effective (~$1/month) |
| **SQLite Database** | Zero-config, ACID compliance, sufficient for personal scale |
| **launchd Orchestration** | Native macOS scheduler, handles sleep/wake correctly |
| **No Broker API** | Fidelity lacks retail API; manual CSV import is reliable and secure |

### 1.3 What This System Does

✅ **Automated Market Monitoring:** Scans prices, news, and sentiment during market hours  
✅ **AI-Powered Analysis:** Uses LLMs to interpret news and generate trade ideas  
✅ **Rigorous Risk Control:** Enforces position sizing, diversification, stop-losses  
✅ **Smart Notifications:** Alerts you via iMessage for urgent items, email for summaries  
✅ **Portfolio Tracking:** Maintains accurate state through Fidelity CSV imports  

### 1.4 What This System Does NOT Do

❌ **Execute Trades:** You maintain 100% control over order execution  
❌ **High-Frequency Trading:** Designed for swing/position trades, not HFT  
❌ **Margin Trading:** Default configuration prohibits leverage (configurable)  
❌ **Short Selling:** Cash account constraints, no shorting (configurable)  

---

## 2. System Architecture

### 2.1 Multi-Agent Event-Driven Design

The system uses a **modular multi-agent architecture** where specialized agents communicate through a shared persistent state (SQLite database). This design pattern provides:

- **Separation of Concerns:** Each agent has a single, clear responsibility
- **Fault Isolation:** Failure in one agent doesn't cascade to others
- **Testability:** Agents can be developed and tested independently
- **Scalability:** Easy to add new agents or replace existing ones

### 2.2 Agent Communication Pattern

```
┌─────────────────┐
│  Market Data    │───┐
│  APIs (Alpaca)  │   │
└─────────────────┘   │
                      │
┌─────────────────┐   │     ┌──────────────────┐
│  News Feeds     │───┼────▶│  Shared State    │
│  (Finnhub)      │   │     │  (SQLite DB)     │
└─────────────────┘   │     └──────────────────┘
                      │              │
┌─────────────────┐   │              │
│  Fidelity CSV   │───┘              │
│  Import         │                  │
└─────────────────┘                  │
                                     ▼
                      ┌──────────────────────────┐
                      │     Agent Pipeline       │
                      │                          │
                      │  1. Market Analyst       │
                      │  2. News Analyst         │
                      │  3. Strategy Planner     │
                      │  4. Risk Controller      │
                      │  5. Notification Agent   │
                      └──────────────────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────┐
                      │   Notification Channels  │
                      │   • iMessage (Urgent)    │
                      │   • Email (Summaries)    │
                      └──────────────────────────┘
```

### 2.3 Agent Roles Summary

| Agent | Primary Function | Inputs | Outputs |
|-------|------------------|--------|---------|
| **Market Analyst** | Real-time price monitoring, technical analysis | Alpaca API, Yahoo Finance | Price alerts, volatility signals, technical indicators |
| **News Analyst** | News aggregation and sentiment extraction | Finnhub, RSS feeds | Structured news events, sentiment scores, ticker mentions |
| **Portfolio Accountant** | State synchronization and P&L tracking | Fidelity CSV exports | Holdings snapshot, cash balance, cost basis |
| **Strategy Planner** | AI-powered trade recommendation synthesis | Market signals, news, portfolio state | Trade candidates with confidence scores |
| **Risk Controller** | Mathematical constraint enforcement | Trade candidates | Validated orders or vetoes with reasons |
| **Notification Specialist** | Multi-channel alert delivery | Validated recommendations | iMessage/Email notifications |

---

## 3. Agent Specifications

### 3.1 Market Analyst Agent

**Purpose:** Transform raw market data into structured intelligence

**Cognitive Tasks:**
1. Fetch real-time price quotes for portfolio holdings + watchlist
2. Calculate technical indicators (SMA, RSI, ATR)
3. Detect significant events (price spikes, volume surges, volatility breakouts)
4. Generate "Market Regime" assessments (Trending, Ranging, High Volatility)

**Implementation Details:**

```python
# File: src/agents/market_analyst.py

import pandas as pd
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import sqlite3

class MarketAnalyst:
    def __init__(self, api_key: str, api_secret: str, db_path: str):
        self.client = StockHistoricalDataClient(api_key, api_secret)
        self.db_path = db_path
        
    def scan_portfolio(self, symbols: list) -> dict:
        """
        Fetch current prices and calculate key metrics
        Returns: dict with symbol -> metrics mapping
        """
        results = {}
        
        for symbol in symbols:
            # Fetch recent data
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=datetime.now() - timedelta(days=1)
            )
            bars = self.client.get_stock_bars(request)
            
            if bars.df.empty:
                continue
                
            df = bars.df
            current_price = df['close'].iloc[-1]
            
            # Calculate ATR for volatility
            atr = self._calculate_atr(df, period=14)
            
            # Calculate moving averages
            sma_50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else None
            
            # Detect price spike (>2x ATR move)
            recent_range = df['high'].iloc[-15:].max() - df['low'].iloc[-15:].min()
            is_volatile = recent_range > (2 * atr)
            
            results[symbol] = {
                'price': float(current_price),
                'atr': float(atr),
                'sma_50': float(sma_50) if sma_50 else None,
                'is_volatile': is_volatile,
                'timestamp': datetime.now().isoformat()
            }
            
            # Write to database
            self._write_to_db(symbol, results[symbol])
            
        return results
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean().iloc[-1]
        
        return atr
    
    def _write_to_db(self, symbol: str, metrics: dict):
        """Persist market data to shared database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO market_data (symbol, price, atr, sma_50, is_volatile, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            metrics['price'],
            metrics['atr'],
            metrics['sma_50'],
            1 if metrics['is_volatile'] else 0,
            metrics['timestamp']
        ))
        
        conn.commit()
        conn.close()
```

**Triggers:**
- **Scheduled:** Every 5 minutes during market hours (6:30 AM - 1:00 PM PT)
- **Event-Driven:** Immediately when a watchlist symbol moves >5% intraday

**Output Example:**
```json
{
  "AAPL": {
    "price": 178.45,
    "atr": 2.34,
    "sma_50": 175.20,
    "is_volatile": false,
    "timestamp": "2026-01-28T10:30:00-08:00"
  }
}
```

---

### 3.2 News Analyst Agent

**Purpose:** Parse financial news and extract actionable intelligence

**Cognitive Tasks:**
1. Aggregate news from multiple sources (Finnhub, RSS feeds)
2. Use Gemini API to extract: ticker mentions, sentiment, implied action
3. Filter for relevance (only portfolio holdings + watchlist)
4. Detect "breaking news" events requiring immediate attention

**Implementation Details:**

```python
# File: src/agents/news_analyst.py

import requests
import feedparser
import google.generativeai as genai
from datetime import datetime
import sqlite3
import json

class NewsAnalyst:
    def __init__(self, finnhub_key: str, gemini_key: str, db_path: str):
        self.finnhub_key = finnhub_key
        self.db_path = db_path
        
        # Configure Gemini
        genai.configure(api_key=gemini_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')  # Fast model for sentiment
        
    def fetch_news(self, symbols: list, lookback_hours: int = 24) -> list:
        """
        Fetch news for specific symbols from Finnhub
        """
        all_news = []
        
        for symbol in symbols:
            url = f"https://finnhub.io/api/v1/company-news"
            params = {
                'symbol': symbol,
                'token': self.finnhub_key,
                'from': self._get_from_date(lookback_hours),
                'to': datetime.now().strftime('%Y-%m-%d')
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                news_items = response.json()
                
                for item in news_items:
                    all_news.append({
                        'symbol': symbol,
                        'headline': item.get('headline'),
                        'summary': item.get('summary'),
                        'source': item.get('source'),
                        'url': item.get('url'),
                        'published': item.get('datetime')
                    })
        
        return all_news
    
    def analyze_sentiment(self, news_item: dict) -> dict:
        """
        Use Gemini to extract structured sentiment from news text
        """
        prompt = f"""You are a financial news analyst. Analyze this news headline and summary.

Headline: {news_item['headline']}
Summary: {news_item.get('summary', 'N/A')}
Stock Ticker: {news_item['symbol']}

Extract the following in JSON format ONLY (no preamble):
{{
  "sentiment": "positive" | "negative" | "neutral",
  "confidence": 0.0-1.0,
  "implied_action": "BUY" | "SELL" | "HOLD",
  "key_reason": "brief explanation in 10 words or less",
  "urgency": "high" | "medium" | "low"
}}

Output ONLY the JSON, no other text."""

        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,  # Low temp for consistency
                max_output_tokens=200
            )
        )
        
        try:
            # Parse JSON from response
            result = json.loads(response.text)
            
            # Add metadata
            result['symbol'] = news_item['symbol']
            result['headline'] = news_item['headline']
            result['timestamp'] = datetime.now().isoformat()
            
            # Write to database
            self._write_to_db(result)
            
            return result
            
        except json.JSONDecodeError:
            # Fallback if LLM doesn't return valid JSON
            return {
                'symbol': news_item['symbol'],
                'sentiment': 'neutral',
                'confidence': 0.0,
                'implied_action': 'HOLD',
                'key_reason': 'parsing_error',
                'urgency': 'low',
                'timestamp': datetime.now().isoformat()
            }
    
    def _write_to_db(self, analysis: dict):
        """Store news analysis in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO news_analysis 
            (symbol, headline, sentiment, confidence, implied_action, key_reason, urgency, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            analysis['symbol'],
            analysis['headline'],
            analysis['sentiment'],
            analysis['confidence'],
            analysis['implied_action'],
            analysis['key_reason'],
            analysis['urgency'],
            analysis['timestamp']
        ))
        
        conn.commit()
        conn.close()
    
    def _get_from_date(self, hours: int) -> str:
        from_dt = datetime.now() - timedelta(hours=hours)
        return from_dt.strftime('%Y-%m-%d')
```

**Triggers:**
- **Scheduled:** Every 15 minutes during market hours
- **Event-Driven:** Immediately on "breaking news" keyword detection

**Output Example:**
```json
{
  "symbol": "AAPL",
  "sentiment": "positive",
  "confidence": 0.85,
  "implied_action": "BUY",
  "key_reason": "Strong iPhone sales in China",
  "urgency": "high",
  "timestamp": "2026-01-28T11:15:00-08:00"
}
```

---

### 3.3 Strategy Planner Agent

**Purpose:** Synthesize all inputs and generate trade recommendations using AI reasoning

**Cognitive Tasks:**
1. Query database for latest market data, news sentiment, and portfolio state
2. Use Gemini Pro (large context model) for complex reasoning
3. Apply Chain-of-Thought prompting to force step-by-step analysis
4. Generate trade hypotheses with confidence scores

**Implementation Details:**

```python
# File: src/agents/strategy_planner.py

import google.generativeai as genai
import sqlite3
import json
from datetime import datetime

class StrategyPlanner:
    def __init__(self, gemini_key: str, db_path: str):
        genai.configure(api_key=gemini_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')  # Pro model for reasoning
        self.db_path = db_path
        
    def generate_recommendation(self, symbol: str) -> dict:
        """
        Generate a trade recommendation for a specific symbol
        Uses Chain-of-Thought prompting for transparency
        """
        
        # Gather context from database
        context = self._gather_context(symbol)
        
        # Construct prompt
        prompt = self._build_cot_prompt(symbol, context)
        
        # Call Gemini
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,  # Moderate randomness for creativity
                max_output_tokens=1000
            )
        )
        
        # Parse response
        try:
            result = json.loads(response.text)
            result['symbol'] = symbol
            result['timestamp'] = datetime.now().isoformat()
            
            # Log to database
            self._write_to_db(result)
            
            return result
            
        except json.JSONDecodeError:
            return None
    
    def _gather_context(self, symbol: str) -> dict:
        """
        Pull all relevant data from database
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest price data
        cursor.execute("""
            SELECT price, atr, sma_50, is_volatile 
            FROM market_data 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (symbol,))
        market_data = cursor.fetchone()
        
        # Get recent news sentiment
        cursor.execute("""
            SELECT sentiment, confidence, implied_action, key_reason
            FROM news_analysis
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (symbol,))
        news_items = cursor.fetchall()
        
        # Get current portfolio position (if any)
        cursor.execute("""
            SELECT quantity, cost_basis, current_value
            FROM holdings h
            JOIN portfolio_snapshot p ON h.snapshot_id = p.id
            WHERE h.symbol = ?
            ORDER BY p.import_timestamp DESC
            LIMIT 1
        """, (symbol,))
        position = cursor.fetchone()
        
        # Get total portfolio equity
        cursor.execute("""
            SELECT total_equity, cash_balance
            FROM portfolio_snapshot
            ORDER BY import_timestamp DESC
            LIMIT 1
        """)
        portfolio = cursor.fetchone()
        
        conn.close()
        
        return {
            'price': market_data[0] if market_data else None,
            'atr': market_data[1] if market_data else None,
            'sma_50': market_data[2] if market_data else None,
            'is_volatile': bool(market_data[3]) if market_data else False,
            'news_sentiment': [
                {'sentiment': n[0], 'confidence': n[1], 'action': n[2], 'reason': n[3]}
                for n in news_items
            ] if news_items else [],
            'current_position': {
                'quantity': position[0] if position else 0,
                'cost_basis': position[1] if position else None,
                'current_value': position[2] if position else None
            },
            'portfolio_equity': portfolio[0] if portfolio else 10000,
            'cash_balance': portfolio[1] if portfolio else 10000
        }
    
    def _build_cot_prompt(self, symbol: str, context: dict) -> str:
        """
        Build Chain-of-Thought prompt to force reasoning transparency
        """
        
        prompt = f"""You are a Senior Financial Analyst evaluating a trade opportunity.

**Task:** Analyze whether to BUY, SELL, or HOLD {symbol}.

**Market Data:**
- Current Price: ${context['price']:.2f}
- 50-Day SMA: ${context['sma_50']:.2f if context['sma_50'] else 'N/A'}
- ATR (Volatility): ${context['atr']:.2f if context['atr'] else 'N/A'}
- High Volatility Warning: {'YES' if context['is_volatile'] else 'NO'}

**Recent News Sentiment:**
{self._format_news(context['news_sentiment'])}

**Current Portfolio Context:**
- Total Equity: ${context['portfolio_equity']:,.2f}
- Cash Available: ${context['cash_balance']:,.2f}
- Existing Position in {symbol}: {context['current_position']['quantity']} shares @ ${context['current_position']['cost_basis']:.2f if context['current_position']['cost_basis'] else 'N/A'}

**Instructions:**
Use the following step-by-step reasoning process:

**Step 1: Technical Analysis**
Evaluate the price trend. Is it above/below SMA? Is momentum clear?

**Step 2: Sentiment Analysis**
Review the news. Is there a clear catalyst? What's the consensus?

**Step 3: Portfolio Risk**
Check position sizing. Would this trade create over-concentration?

**Step 4: Final Recommendation**
Based on the above, what action do you recommend?

**Output Format (JSON ONLY, no preamble):**
{{
  "step1_technical": "Your technical analysis in 20 words",
  "step2_sentiment": "Your sentiment analysis in 20 words",
  "step3_risk": "Your risk assessment in 20 words",
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "Final justification in 30 words",
  "target_price": null or number (for BUY/SELL),
  "stop_loss": null or number (for BUY)
}}
"""
        return prompt
    
    def _format_news(self, news_items: list) -> str:
        """Format news for prompt"""
        if not news_items:
            return "No recent significant news."
        
        formatted = []
        for item in news_items:
            formatted.append(
                f"- {item['sentiment'].upper()} (confidence: {item['confidence']:.0%}): {item['reason']}"
            )
        return "\n".join(formatted)
    
    def _write_to_db(self, recommendation: dict):
        """Store recommendation for audit trail"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO strategy_recommendations
            (symbol, action, confidence, reasoning, target_price, stop_loss, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            recommendation['symbol'],
            recommendation['action'],
            recommendation['confidence'],
            recommendation['reasoning'],
            recommendation.get('target_price'),
            recommendation.get('stop_loss'),
            recommendation['timestamp']
        ))
        
        conn.commit()
        conn.close()
```

**Chain-of-Thought Reasoning:**
The prompt forces the LLM to articulate its reasoning in discrete steps, which:
1. Improves output quality (forces structured thinking)
2. Provides transparency (you can see *why* it recommends something)
3. Enables debugging (if a recommendation is bad, you can trace which step failed)

---

### 3.4 Risk Controller Agent

**Purpose:** Enforce mathematical constraints and veto unsafe trades

**This is NOT an AI agent** - it's pure deterministic Python logic. No LLM hallucinations allowed in risk management.

**Hard Constraints:**
1. **Cash Constraint:** `trade_cost ≤ available_cash`
2. **Position Size Limit:** `position_value ≤ 20% of portfolio_equity`
3. **Sector Exposure Cap:** `sector_total ≤ 40% of portfolio_equity`
4. **No Shorting:** `final_quantity ≥ 0`
5. **Volatility Filter:** Reject if `ATR > 10% of price` (extreme volatility)

**Implementation:**

```python
# File: src/agents/risk_controller.py

import sqlite3
from typing import Optional

class RiskController:
    def __init__(self, db_path: str):
        self.db_path = db_path
        
        # Configuration (can be loaded from config file)
        self.MAX_POSITION_SIZE_PCT = 0.20  # 20% of equity
        self.MAX_SECTOR_EXPOSURE_PCT = 0.40  # 40% of equity
        self.MAX_VOLATILITY_PCT = 0.10  # 10% ATR relative to price
        self.RISK_PER_TRADE_PCT = 0.015  # 1.5% of equity at risk per trade
        
    def validate_trade(self, recommendation: dict) -> dict:
        """
        Validate a trade recommendation against all risk rules
        Returns: dict with 'approved': bool, 'reason': str, 'adjusted_quantity': int
        """
        
        symbol = recommendation['symbol']
        action = recommendation['action']
        
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
            result = {'approved': False, 'reason': 'Invalid action'}
        
        # Log decision
        self._log_decision(recommendation, result)
        
        return result
    
    def _validate_buy(self, symbol: str, rec: dict, context: dict) -> dict:
        """
        Validate a BUY recommendation
        """
        
        price = context['price']
        atr = context['atr']
        equity = context['portfolio_equity']
        cash = context['cash_balance']
        current_position_value = context['current_position_value']
        sector = context['sector']
        sector_exposure = context['sector_exposure']
        
        # Calculate position size using Fixed Fractional method
        risk_amount = equity * self.RISK_PER_TRADE_PCT  # $10k * 1.5% = $150
        
        # Stop loss based on ATR
        stop_loss = rec.get('stop_loss')
        if not stop_loss:
            # Default: 2.5x ATR below entry
            stop_loss = price - (2.5 * atr)
        
        risk_per_share = price - stop_loss
        
        if risk_per_share <= 0:
            return {
                'approved': False,
                'reason': 'Stop loss is above entry price (invalid setup)'
            }
        
        # Calculate shares based on risk
        proposed_shares = int(risk_amount / risk_per_share)
        proposed_cost = proposed_shares * price
        
        # Check 1: Sufficient cash?
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
        
        # Check 2: Position size limit
        new_position_value = current_position_value + proposed_cost
        if new_position_value > (equity * self.MAX_POSITION_SIZE_PCT):
            max_allowed_cost = (equity * self.MAX_POSITION_SIZE_PCT) - current_position_value
            if max_allowed_cost < price:
                return {
                    'approved': False,
                    'reason': f'Position size limit. {symbol} would exceed {self.MAX_POSITION_SIZE_PCT*100:.0f}% of portfolio'
                }
            adjusted_shares = int(max_allowed_cost / price)
            proposed_shares = adjusted_shares
            proposed_cost = proposed_shares * price
        
        # Check 3: Sector exposure
        new_sector_exposure = sector_exposure + proposed_cost
        if new_sector_exposure > (equity * self.MAX_SECTOR_EXPOSURE_PCT):
            return {
                'approved': False,
                'reason': f'Sector limit. {sector} exposure would exceed {self.MAX_SECTOR_EXPOSURE_PCT*100:.0f}%'
            }
        
        # Check 4: Volatility filter
        if atr / price > self.MAX_VOLATILITY_PCT:
            return {
                'approved': False,
                'reason': f'Excessive volatility. ATR is {atr/price*100:.1f}% of price'
            }
        
        # Approved!
        return {
            'approved': True,
            'reason': 'All risk checks passed',
            'approved_shares': proposed_shares,
            'approved_cost': proposed_cost,
            'calculated_stop_loss': stop_loss,
            'risk_per_trade': risk_amount
        }
    
    def _validate_sell(self, symbol: str, rec: dict, context: dict) -> dict:
        """
        Validate a SELL recommendation
        """
        
        current_quantity = context['current_quantity']
        
        if current_quantity <= 0:
            return {
                'approved': False,
                'reason': 'Cannot sell. No position held.'
            }
        
        # For sells, we typically close the full position
        # (Partial sells could be implemented but add complexity)
        
        return {
            'approved': True,
            'reason': 'Sell approved',
            'approved_shares': current_quantity
        }
    
    def _get_risk_context(self, symbol: str) -> dict:
        """
        Fetch all data needed for risk calculations
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get market data
        cursor.execute("""
            SELECT price, atr
            FROM market_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol,))
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
            SELECT h.quantity, h.current_value, s.sector
            FROM holdings h
            JOIN portfolio_snapshot p ON h.snapshot_id = p.id
            JOIN stock_metadata s ON h.symbol = s.symbol
            WHERE h.symbol = ?
            ORDER BY p.import_timestamp DESC
            LIMIT 1
        """, (symbol,))
        position = cursor.fetchone()
        
        # Get sector exposure
        cursor.execute("""
            SELECT s.sector
            FROM stock_metadata s
            WHERE s.symbol = ?
        """, (symbol,))
        sector_row = cursor.fetchone()
        sector = sector_row[0] if sector_row else 'Unknown'
        
        cursor.execute("""
            SELECT SUM(h.current_value)
            FROM holdings h
            JOIN portfolio_snapshot p ON h.snapshot_id = p.id
            JOIN stock_metadata s ON h.symbol = s.symbol
            WHERE s.sector = ?
            AND p.id = (SELECT id FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 1)
        """, (sector,))
        sector_exp = cursor.fetchone()
        
        conn.close()
        
        return {
            'price': market[0] if market else 0,
            'atr': market[1] if market else 0,
            'portfolio_equity': portfolio[0] if portfolio else 10000,
            'cash_balance': portfolio[1] if portfolio else 10000,
            'current_quantity': position[0] if position else 0,
            'current_position_value': position[1] if position else 0,
            'sector': sector,
            'sector_exposure': sector_exp[0] if sector_exp[0] else 0
        }
    
    def _log_decision(self, recommendation: dict, result: dict):
        """
        Log all risk decisions for audit trail
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO risk_decisions
            (symbol, action, approved, reason, approved_shares, timestamp)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            recommendation['symbol'],
            recommendation['action'],
            1 if result['approved'] else 0,
            result['reason'],
            result.get('approved_shares')
        ))
        
        conn.commit()
        conn.close()
```

**Position Sizing Formula:**

```
Risk_Amount = Portfolio_Equity × Risk_Per_Trade%
             = $10,000 × 1.5% = $150

Stop_Loss = Entry_Price - (2.5 × ATR)

Risk_Per_Share = Entry_Price - Stop_Loss

Shares = Risk_Amount / Risk_Per_Share

Example:
- Stock: $100
- ATR: $2
- Stop: $100 - (2.5 × $2) = $95
- Risk/Share: $100 - $95 = $5
- Shares: $150 / $5 = 30 shares
- Total Cost: 30 × $100 = $3,000 (30% of $10k portfolio)
```

---

### 3.5 Notification Specialist Agent

**Purpose:** Deliver alerts to you through appropriate channels

**Channel Selection Logic:**

| Urgency | Condition | Channel | Timing |
|---------|-----------|---------|--------|
| **Critical** | Position down >10%, Risk breach, Stop-loss hit | iMessage | Immediate |
| **High** | New trade recommendation | iMessage | During market hours only |
| **Medium** | Position update, News alert | Email | Batched hourly |
| **Low** | Daily summary, Performance report | Email | End of day (2:00 PM PT) |

**Implementation:**

```python
# File: src/agents/notification_specialist.py

import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time
import sqlite3

class NotificationSpecialist:
    def __init__(self, db_path: str, config: dict):
        self.db_path = db_path
        self.config = config
        
        # Quiet hours (no iMessage alerts)
        self.quiet_start = time(21, 0)  # 9:00 PM
        self.quiet_end = time(6, 0)     # 6:00 AM
        
    def send_trade_alert(self, recommendation: dict, risk_result: dict):
        """
        Send a trade recommendation to the user
        """
        
        if not risk_result['approved']:
            # Trade was vetoed - log but don't alert (unless critical)
            return
        
        # Format message
        message = self._format_trade_message(recommendation, risk_result)
        
        # Check if we should send (market hours, not quiet hours)
        if self._should_send_imessage():
            self._send_imessage(message)
        else:
            # Queue for next allowed time or send via email
            self._send_email(
                subject="[Queued Alert] Trade Recommendation",
                body=message
            )
    
    def _format_trade_message(self, rec: dict, risk: dict) -> str:
        """
        Format a clean, actionable message
        """
        
        action = rec['action']
        symbol = rec['symbol']
        confidence = rec['confidence']
        reasoning = rec['reasoning']
        
        shares = risk.get('approved_shares', 0)
        cost = risk.get('approved_cost', 0)
        stop_loss = risk.get('calculated_stop_loss')
        
        msg = f"""📊 TRADE ALERT - {action} {symbol}

💡 Recommendation: {action} {shares} shares @ market
📈 Confidence: {confidence:.0%}
🎯 Reasoning: {reasoning}

💰 Portfolio Impact:
   • Cost: ${cost:,.2f}
   • Stop Loss: ${stop_loss:.2f} (−{((rec.get('target_price', 0) - stop_loss) / rec.get('target_price', 1) * 100):.1f}%)
   
⚠️ Risk: ${risk.get('risk_per_trade', 0):.2f} (1.5% of portfolio)

Reply with action taken or 'SKIP' to dismiss.
System Time: {datetime.now().strftime('%I:%M %p PT')}"""

        return msg
    
    def _send_imessage(self, message: str):
        """
        Send via macOS Messages app using AppleScript
        """
        
        # Get phone number from config
        recipient = self.config.get('imessage_recipient')
        
        # Escape quotes in message
        escaped_msg = message.replace('"', '\\"').replace("'", "\\'")
        
        # AppleScript to send message
        script = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{recipient}" of targetService
            send "{escaped_msg}" to targetBuddy
        end tell
        '''
        
        try:
            subprocess.run(['osascript', '-e', script], check=True)
            self._log_notification('iMessage', message, 'sent')
        except subprocess.CalledProcessError as e:
            self._log_notification('iMessage', message, 'failed')
            # Fallback to email
            self._send_email(
                subject="[URGENT] Trade Alert - iMessage Failed",
                body=message
            )
    
    def _send_email(self, subject: str, body: str, is_html: bool = False):
        """
        Send via Gmail SMTP
        """
        
        smtp_user = self.config.get('gmail_user')
        smtp_pass = self.config.get('gmail_app_password')
        recipient = self.config.get('email_recipient')
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = recipient
        
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            self._log_notification('email', subject, 'sent')
        except Exception as e:
            self._log_notification('email', subject, f'failed: {str(e)}')
    
    def _should_send_imessage(self) -> bool:
        """
        Check if it's appropriate to send iMessage
        """
        now = datetime.now().time()
        
        # Check quiet hours
        if self.quiet_start <= now or now <= self.quiet_end:
            return False
        
        # Check market hours (6:30 AM - 1:00 PM PT)
        market_open = time(6, 30)
        market_close = time(13, 0)
        
        if not (market_open <= now <= market_close):
            return False
        
        return True
    
    def _log_notification(self, channel: str, content: str, status: str):
        """
        Log all notifications for debugging
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO notification_log
            (channel, content, status, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        """, (channel, content, status))
        
        conn.commit()
        conn.close()
    
    def send_daily_summary(self):
        """
        Send end-of-day performance report via email
        """
        
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
    
    def _generate_daily_summary(self) -> dict:
        """
        Query database for daily performance metrics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get today's recommendations
        cursor.execute("""
            SELECT symbol, action, confidence, reasoning
            FROM strategy_recommendations
            WHERE DATE(timestamp) = DATE('now')
        """)
        recommendations = cursor.fetchall()
        
        # Get portfolio value change
        cursor.execute("""
            SELECT total_equity
            FROM portfolio_snapshot
            ORDER BY import_timestamp DESC
            LIMIT 2
        """)
        equity_rows = cursor.fetchall()
        
        current_equity = equity_rows[0][0] if equity_rows else 10000
        previous_equity = equity_rows[1][0] if len(equity_rows) > 1 else 10000
        daily_change = current_equity - previous_equity
        daily_change_pct = (daily_change / previous_equity) * 100
        
        conn.close()
        
        return {
            'recommendations': recommendations,
            'current_equity': current_equity,
            'daily_change': daily_change,
            'daily_change_pct': daily_change_pct
        }
    
    def _format_html_summary(self, summary: dict) -> str:
        """
        Create HTML-formatted email body
        """
        
        html = f"""
        <html>
          <head>
            <style>
              body {{ font-family: Arial, sans-serif; }}
              .header {{ background-color: #1a73e8; color: white; padding: 20px; }}
              .metrics {{ margin: 20px; }}
              .positive {{ color: green; }}
              .negative {{ color: red; }}
              table {{ border-collapse: collapse; width: 100%; }}
              th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
              th {{ background-color: #f2f2f2; }}
            </style>
          </head>
          <body>
            <div class="header">
              <h1>Daily Trading Summary</h1>
              <p>{datetime.now().strftime('%A, %B %d, %Y')}</p>
            </div>
            
            <div class="metrics">
              <h2>Portfolio Performance</h2>
              <p>Current Equity: <strong>${summary['current_equity']:,.2f}</strong></p>
              <p>Daily Change: <span class="{'positive' if summary['daily_change'] >= 0 else 'negative'}">
                ${summary['daily_change']:+,.2f} ({summary['daily_change_pct']:+.2f}%)
              </span></p>
            </div>
            
            <div class="metrics">
              <h2>Today's Recommendations</h2>
              {'<p>No recommendations generated today.</p>' if not summary['recommendations'] else ''}
              <table>
                <tr>
                  <th>Symbol</th>
                  <th>Action</th>
                  <th>Confidence</th>
                  <th>Reasoning</th>
                </tr>
"""
        
        for rec in summary['recommendations']:
            html += f"""
                <tr>
                  <td>{rec[0]}</td>
                  <td><strong>{rec[1]}</strong></td>
                  <td>{rec[2]:.0%}</td>
                  <td>{rec[3]}</td>
                </tr>
"""
        
        html += """
              </table>
            </div>
          </body>
        </html>
        """
        
        return html
```

**iMessage Setup Requirements:**
1. Enable "Messages" in System Settings → Privacy & Security → Automation
2. Grant Terminal/Python access to control Messages
3. Ensure your Mac is signed into iMessage with your Apple ID

---

## 4. Data Layer

### 4.1 API Source Strategy

**Primary Source: Alpaca Markets (Free Tier)**
- **Pros:** Clean API, IEX data, Python SDK, reliable uptime
- **Cons:** IEX has lower volume than consolidated tape (sufficient for swing trading)
- **Usage:** Real-time quotes, historical bars, watchlist monitoring

**Secondary Source: Yahoo Finance (yfinance)**
- **Pros:** Free, broad coverage, no API key needed
- **Cons:** Rate-limited, unofficial (scraping), can be unstable
- **Usage:** Backup data, sector information, dividend dates

**News Source: Finnhub (Free Tier)**
- **Pros:** 60 calls/minute, company news, sentiment API
- **Cons:** Limited historical depth on free tier
- **Usage:** Real-time news headlines, earnings calendar

### 4.2 The Grounding Protocol (Preventing AI Hallucinations)

**Critical Rule:** The AI never retrieves or calculates numeric data. It only reasons about data provided to it.

**Bad Approach (Hallucination Risk):**
```python
# ❌ NEVER DO THIS
prompt = "What is the current price of Apple stock?"
response = gemini_model.generate(prompt)
price = float(response.text)  # HALLUCINATED!
```

**Correct Approach (Grounded Data):**
```python
# ✅ ALWAYS DO THIS
# Step 1: Fetch real data
real_price = alpaca_client.get_latest_quote('AAPL').ask_price

# Step 2: Inject into prompt
prompt = f"""
You are analyzing AAPL.
VERIFIED DATA (do not question these numbers):
- Current Price: ${real_price:.2f}
- Source: Alpaca IEX (timestamp: {datetime.now()})

Based on this VERIFIED price, analyze...
"""
response = gemini_model.generate(prompt)
```

**Validation Layer:**
Any numeric value in the AI's output must be cross-referenced against the database. If the AI mentions a price that doesn't match our cached data, the system flags it as a "Data Anomaly" and rejects the recommendation.

### 4.3 Data Caching Strategy

**Purpose:** 
- Minimize API calls (respect rate limits)
- Ensure all agents see the same data snapshot
- Enable offline analysis if APIs are down

**Implementation:**
```python
# File: src/data/cache_manager.py

import sqlite3
from datetime import datetime, timedelta

class CacheManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.CACHE_TTL_SECONDS = 300  # 5 minutes for market hours
        
    def get_cached_price(self, symbol: str) -> float:
        """
        Retrieve price from cache if fresh, otherwise return None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT price, timestamp
            FROM market_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        price, timestamp = row
        cache_time = datetime.fromisoformat(timestamp)
        
        # Check if cache is fresh
        if datetime.now() - cache_time < timedelta(seconds=self.CACHE_TTL_SECONDS):
            return price
        
        return None
    
    def cache_price(self, symbol: str, price: float):
        """
        Store price in cache
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO market_data (symbol, price, timestamp)
            VALUES (?, ?, ?)
        """, (symbol, price, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
```

**Cache Invalidation:**
- Automatically expire after 5 minutes during market hours
- Force refresh after major events (e.g., earnings release detected)

---

## 5. Risk Management Engine

### 5.1 Position Sizing: Fixed Fractional Method

**Formula:**
```
Risk_Amount = Portfolio_Equity × Risk_Per_Trade_Percentage

Stop_Loss_Price = Entry_Price - (Multiplier × ATR)

Risk_Per_Share = Entry_Price - Stop_Loss_Price

Number_of_Shares = floor(Risk_Amount / Risk_Per_Share)

Total_Position_Cost = Number_of_Shares × Entry_Price
```

**Example Calculation:**
```
Portfolio: $10,000
Risk Per Trade: 1.5% → $150
Symbol: MSFT
Entry Price: $400
ATR(14): $8
Stop Loss: $400 - (2.5 × $8) = $380
Risk Per Share: $400 - $380 = $20

Shares = floor($150 / $20) = 7 shares
Total Cost = 7 × $400 = $2,800 (28% of portfolio)
```

**Adjustments:**
If total cost exceeds available cash or position size limits, reduce shares proportionally.

### 5.2 Hard Constraint Checklist

Before ANY trade is approved, it must pass ALL of these checks:

| # | Constraint | Formula | Rejection Reason |
|---|------------|---------|------------------|
| 1 | **Cash Available** | `trade_cost ≤ cash_balance` | "Insufficient funds" |
| 2 | **Position Size** | `new_position_value ≤ 0.20 × equity` | "Exceeds 20% position limit" |
| 3 | **Sector Exposure** | `sector_total ≤ 0.40 × equity` | "Sector over-concentration" |
| 4 | **No Shorting** | `final_shares ≥ 0` | "Short selling not allowed" |
| 5 | **Volatility Filter** | `ATR / price ≤ 0.10` | "Excessive volatility" |
| 6 | **Minimum Liquidity** | `avg_volume_20d ≥ 200,000` | "Low liquidity risk" |

### 5.3 Dynamic Stop-Loss Calculation

**ATR-Based Stops:**
```
Stop_Loss = Entry - (2.5 × ATR)
```

**Why 2.5× ATR?**
- 1× ATR: Too tight, triggers on normal volatility
- 2× ATR: Better, but still noisy
- 2.5× ATR: Optimal balance (gives stock room to breathe)
- 3× ATR: Too loose, risk too much capital

**Trailing Stop (Optional Enhancement):**
Once a position is profitable, trail the stop:
```
Trailing_Stop = max(Original_Stop, Current_Price - (2.5 × ATR))
```

---

## 6. AI Integration Strategy

### 6.1 Why Gemini API (Paid Tier)?

**Privacy Requirements:**
- **Free Tier:** Google may use your inputs/outputs to improve models
- **Paid Tier:** Explicit guarantee that your data is NOT used for training
- **Cost:** ~$1-2/month for personal use (50k tokens/day)

**Context Window:**
- Gemini 1.5 Pro: 1M+ token context
- Allows passing weeks of news articles or full earnings transcripts

### 6.2 Model Routing Matrix

| Task | Model | Temperature | Max Tokens | Rationale |
|------|-------|-------------|------------|-----------|
| **Strategy Synthesis** | gemini-1.5-pro | 0.3 | 1000 | Complex reasoning, needs creativity |
| **News Sentiment** | gemini-1.5-flash | 0.1 | 200 | Simple classification, fast |
| **JSON Formatting** | gemini-1.5-flash | 0.0 | 100 | Deterministic output required |
| **Math/Calculations** | Local Python | N/A | N/A | Never trust LLM for arithmetic |

### 6.3 Chain-of-Thought Prompting

**Why?**
Forcing the model to articulate its reasoning in steps improves:
1. Output quality (structured thinking)
2. Transparency (you see the logic)
3. Debuggability (identify which reasoning step failed)

**Template:**
```
You are analyzing [TASK].

Step 1: [Analyze technical setup]
Step 2: [Analyze sentiment/news]
Step 3: [Check portfolio risk]
Step 4: [Final recommendation]

Output in JSON format:
{
  "step1": "your analysis",
  "step2": "your analysis",
  "step3": "your analysis",
  "action": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0
}
```

---

## 7. macOS Automation

### 7.1 launchd Configuration

**Why launchd instead of cron?**
- cron is deprecated on macOS
- launchd handles sleep/wake correctly
- Integrated with macOS system state

**Plist File: `com.user.stockagent.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" 
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Label (must match filename without .plist) -->
    <key>Label</key>
    <string>com.user.stockagent</string>
    
    <!-- Program to run -->
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/StockAgent/venv/bin/python3</string>
        <string>/Users/YOUR_USERNAME/StockAgent/src/main_orchestrator.py</string>
    </array>
    
    <!-- Environment Variables (API keys, paths) -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/YOUR_USERNAME/StockAgent</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    
    <!-- Logging -->
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/StockAgent/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/StockAgent/logs/stderr.log</string>
    
    <!-- Schedule: Pre-market scan at 6:00 AM PT -->
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>6</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>6</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>13</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>
    
    <!-- Don't run at system boot, only on schedule -->
    <key>RunAtLoad</key>
    <false/>
    
    <!-- Don't keep retrying if it fails -->
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
```

**Deployment Commands:**
```bash
# Copy plist to LaunchAgents directory
cp com.user.stockagent.plist ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/com.user.stockagent.plist

# Check status
launchctl list | grep stockagent

# Unload (to stop)
launchctl unload ~/Library/LaunchAgents/com.user.stockagent.plist

# Force run now (for testing)
launchctl start com.user.stockagent
```

### 7.2 Handling Sleep/Wake

**Problem:** If your Mac is asleep at 6:00 AM (scheduled time), the job is skipped.

**Solution:** launchd "coalesces" missed events. When the Mac wakes, it fires the job immediately.

**Implication:** Your Python script must check the current time and determine context:

```python
# File: src/main_orchestrator.py

import pytz
from datetime import datetime

def main():
    # Get current time in PT
    pt_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pt_tz)
    
    hour = now.hour
    
    if 6 <= hour < 7:
        # Pre-market mode
        print("Running pre-market scan...")
        run_premarket_analysis()
        
    elif 7 <= hour < 13:
        # Market hours mode
        print("Running intraday monitoring...")
        run_intraday_scan()
        
    elif 13 <= hour < 14:
        # Post-market mode
        print("Running post-market analysis...")
        run_postmarket_summary()
        
    else:
        # Outside market hours
        print(f"Outside market hours ({now.strftime('%I:%M %p')}). Skipping.")
        return

if __name__ == "__main__":
    main()
```

### 7.3 File System Watchdog for CSV Imports

**Purpose:** Automatically detect when you drop a Fidelity CSV into the inbox folder.

**Implementation:**
```python
# File: src/utils/watchdog_csv.py

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
from pathlib import Path

class CSVHandler(FileSystemEventHandler):
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = Path(event.src_path)
        
        # Check if it's a CSV file
        if filepath.suffix.lower() == '.csv':
            print(f"Detected new file: {filepath.name}")
            
            # Trigger portfolio import
            from agents.portfolio_accountant import PortfolioAccountant
            accountant = PortfolioAccountant(self.db_path)
            accountant.import_fidelity_csv(str(filepath))

def start_watchdog(inbox_path: str, db_path: str):
    event_handler = CSVHandler(db_path)
    observer = Observer()
    observer.schedule(event_handler, inbox_path, recursive=False)
    observer.start()
    
    try:
        print(f"Watching for CSV files in: {inbox_path}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    INBOX = "/Users/YOUR_USERNAME/StockAgent/inbox"
    DB = "/Users/YOUR_USERNAME/StockAgent/data/agent.db"
    start_watchdog(INBOX, DB)
```

**Run as Background Service:**
Create a second launchd plist for the watchdog:

```xml
<!-- File: com.user.stockagent.watchdog.plist -->
<key>ProgramArguments</key>
<array>
    <string>/Users/YOUR_USERNAME/StockAgent/venv/bin/python3</string>
    <string>/Users/YOUR_USERNAME/StockAgent/src/utils/watchdog_csv.py</string>
</array>

<key>KeepAlive</key>
<true/>  <!-- Keep running continuously -->

<key>RunAtLoad</key>
<true/>  <!-- Start on login -->
```

---

## 8. Portfolio Management

### 8.1 Fidelity CSV Format

Fidelity exports positions in a standardized CSV format. Here's the expected structure:

**Sample CSV:**
```csv
Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,AAPL,APPLE INC,50,178.45,8922.50,8500.00,170.00,422.50,4.97,Cash
Z12345678,Individual,MSFT,MICROSOFT CORP,20,380.20,7604.00,7200.00,360.00,404.00,5.61,Cash
Z12345678,Individual,SPAXX,FIDELITY GOVERNMENT MONEY MARKET,3500.00,1.00,3500.00,3500.00,1.00,0.00,0.00,Cash
```

**Key Columns:**
- **Symbol:** Ticker (special case: `SPAXX` = cash)
- **Quantity:** Number of shares
- **Last Price:** Current market price
- **Cost Basis Total:** Total amount paid for position
- **Cost Basis Per Share:** Average purchase price

### 8.2 Portfolio Accountant Implementation

```python
# File: src/agents/portfolio_accountant.py

import pandas as pd
import sqlite3
from datetime import datetime

class PortfolioAccountant:
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def import_fidelity_csv(self, csv_path: str):
        """
        Parse Fidelity CSV and update database
        """
        
        # Read CSV
        df = pd.read_csv(csv_path)
        
        # Create new snapshot
        snapshot_id = self._create_snapshot()
        
        # Process each row
        for _, row in df.iterrows():
            symbol = row['Symbol']
            
            # Handle cash (Fidelity uses SPAXX for money market)
            if symbol in ['SPAXX', 'CORE', 'FDRXX']:  # Common cash symbols
                cash_balance = row['Current Value']
                self._update_cash(snapshot_id, cash_balance)
            else:
                # Regular equity position
                self._add_holding(
                    snapshot_id=snapshot_id,
                    symbol=symbol,
                    quantity=row['Quantity'],
                    cost_basis=row['Cost Basis Per Share'],
                    current_value=row['Current Value']
                )
        
        # Calculate total equity
        self._finalize_snapshot(snapshot_id)
        
        print(f"Portfolio imported successfully. Snapshot ID: {snapshot_id}")
        
        # Run reconciliation
        self._reconcile_with_previous()
    
    def _create_snapshot(self) -> int:
        """
        Create new snapshot entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO portfolio_snapshot (import_timestamp, total_equity, cash_balance)
            VALUES (?, 0, 0)
        """, (datetime.now().isoformat(),))
        
        snapshot_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return snapshot_id
    
    def _add_holding(self, snapshot_id: int, symbol: str, quantity: float, 
                     cost_basis: float, current_value: float):
        """
        Add holding to snapshot
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO holdings (snapshot_id, symbol, quantity, cost_basis, current_value)
            VALUES (?, ?, ?, ?, ?)
        """, (snapshot_id, symbol, quantity, cost_basis, current_value))
        
        conn.commit()
        conn.close()
    
    def _update_cash(self, snapshot_id: int, cash_balance: float):
        """
        Update cash balance for snapshot
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE portfolio_snapshot
            SET cash_balance = ?
            WHERE id = ?
        """, (cash_balance, snapshot_id))
        
        conn.commit()
        conn.close()
    
    def _finalize_snapshot(self, snapshot_id: int):
        """
        Calculate total equity for snapshot
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(current_value) 
            FROM holdings 
            WHERE snapshot_id = ?
        """, (snapshot_id,))
        
        holdings_value = cursor.fetchone()[0] or 0
        
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
        conn.close()
    
    def _reconcile_with_previous(self):
        """
        Compare new snapshot with previous to detect trades
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get last 2 snapshots
        cursor.execute("""
            SELECT id FROM portfolio_snapshot
            ORDER BY import_timestamp DESC
            LIMIT 2
        """)
        
        snapshots = cursor.fetchall()
        
        if len(snapshots) < 2:
            print("No previous snapshot to compare.")
            conn.close()
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
                print(f"📈 Detected BUY: {symbol} +{delta} shares")
                self._log_inferred_trade(symbol, 'BUY', delta, new_id)
            elif delta < 0:
                print(f"📉 Detected SELL: {symbol} {delta} shares")
                self._log_inferred_trade(symbol, 'SELL', abs(delta), new_id)
        
        conn.close()
    
    def _log_inferred_trade(self, symbol: str, action: str, quantity: float, snapshot_id: int):
        """
        Log inferred trade to audit trail
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO trade_log (symbol, action, quantity, snapshot_id, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, action, quantity, snapshot_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
```

### 8.3 State Diffing Algorithm

**Purpose:** Infer trades by comparing two snapshots.

**Logic:**
```
Old Snapshot: {AAPL: 50, MSFT: 20}
New Snapshot: {AAPL: 60, MSFT: 10, TSLA: 15}

Inferred Trades:
- BUY 10 AAPL (50 → 60)
- SELL 10 MSFT (20 → 10)
- BUY 15 TSLA (new position)
```

This maintains a complete trade history without manual entry.

---

## 9. User Experience & Notifications

### 9.1 Notification Hierarchy

| Level | Condition | Channel | Example |
|-------|-----------|---------|---------|
| 🚨 **CRITICAL** | Stop-loss hit, Portfolio down >10%, Risk breach | iMessage | "🚨 AAPL hit stop-loss at $140. Position closed." |
| ⚠️ **HIGH** | New trade recommendation, Position up/down >5% | iMessage | "⚠️ BUY 30 AAPL @ $178. Confidence: 85%" |
| ℹ️ **MEDIUM** | News alert, Earnings upcoming | Email (hourly batch) | "ℹ️ MSFT earnings tomorrow PM" |
| 📊 **LOW** | Daily summary, Weekly performance | Email (EOD) | "📊 Portfolio +2.3% this week" |

### 9.2 Message Templates

**Trade Recommendation (iMessage):**
```
📊 TRADE ALERT - BUY AAPL

💡 Action: BUY 30 shares @ market
📈 Confidence: 85%
🎯 Reasoning: Strong earnings, pullback to SMA50

💰 Portfolio Impact:
   • Cost: $5,350
   • New Position: 18% of portfolio
   • Stop Loss: $165 (-7.5%)
   
⚠️ Risk: $150 (1.5% of portfolio)

Reply 'DONE' when executed.
10:45 AM PT
```

**Daily Summary (Email HTML):**
```html
<h1>📈 Daily Market Summary</h1>
<p>Tuesday, January 28, 2026</p>

<h2>Portfolio Performance</h2>
<table>
  <tr><td>Current Equity:</td><td>$10,450</td></tr>
  <tr><td>Daily Change:</td><td style="color:green">+$230 (+2.2%)</td></tr>
  <tr><td>Cash Available:</td><td>$3,200</td></tr>
</table>

<h2>Today's Activity</h2>
<ul>
  <li>✅ BUY 30 AAPL executed @ $178.20</li>
  <li>📰 MSFT announces new AI product (positive sentiment)</li>
</ul>

<h2>Tomorrow's Watch</h2>
<ul>
  <li>TSLA earnings after close</li>
  <li>Fed interest rate decision 2:00 PM</li>
</ul>
```

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Build core infrastructure and prove data flow works.

**Week 1 Tasks:**
- [ ] Set up Python virtual environment
- [ ] Install dependencies (`requirements.txt`)
- [ ] Create SQLite database with all schemas
- [ ] Implement `PortfolioAccountant` CSV parser
- [ ] Test: Import a sample Fidelity CSV

**Week 2 Tasks:**
- [ ] Set up Alpaca API account (free tier)
- [ ] Implement `MarketAnalyst` price fetching
- [ ] Implement cache layer (`CacheManager`)
- [ ] Test: Fetch prices for 5 stocks, verify in database

**Deliverable:** 
A script that:
1. Reads a Fidelity CSV
2. Fetches current prices for those symbols
3. Displays portfolio value in terminal

```bash
$ python src/test_phase1.py

Portfolio Snapshot:
-----------------------
AAPL: 50 shares @ $178.45 = $8,922.50
MSFT: 20 shares @ $380.20 = $7,604.00
Cash: $3,500.00
-----------------------
Total Equity: $20,026.50
```

---

### Phase 2: Intelligence Layer (Weeks 3-4)

**Goal:** Integrate AI and generate first recommendations.

**Week 3 Tasks:**
- [ ] Set up Google Cloud project and Gemini API key
- [ ] Implement `NewsAnalyst` with Finnhub integration
- [ ] Test sentiment extraction on 10 news articles
- [ ] Verify JSON parsing from Gemini responses

**Week 4 Tasks:**
- [ ] Implement `StrategyPlanner` with Chain-of-Thought prompts
- [ ] Implement `RiskController` with all constraint checks
- [ ] Test end-to-end: News → Analysis → Recommendation → Risk Veto
- [ ] Create mock recommendations and verify risk calculations

**Deliverable:**
A script that generates a trade recommendation:

```bash
$ python src/test_phase2.py --symbol AAPL

Recommendation Generated:
--------------------------
Symbol: AAPL
Action: BUY
Confidence: 0.87
Reasoning: Strong earnings beat, technical breakout above SMA50
Proposed Shares: 30
Cost: $5,350
Stop Loss: $165
Risk: $150

Risk Controller: ✅ APPROVED
```

---

### Phase 3: Automation & Notifications (Weeks 5-6)

**Goal:** Deploy as background service with user notifications.

**Week 5 Tasks:**
- [ ] Create launchd plist configuration
- [ ] Test scheduled execution (run at specific times)
- [ ] Implement `NotificationSpecialist`
- [ ] Set up iMessage integration (test with yourself)
- [ ] Set up Gmail SMTP (app password)

**Week 6 Tasks:**
- [ ] Implement file watchdog for CSV auto-import
- [ ] Create `main_orchestrator.py` with time-based logic
- [ ] Deploy to `~/Library/LaunchAgents`
- [ ] Run for 3 days in "paper trading" mode (log-only, no alerts)
- [ ] Fix any bugs discovered during live testing

**Deliverable:**
Fully autonomous system that:
1. Runs pre-market scan at 6:00 AM
2. Monitors market during trading hours
3. Sends iMessage alerts for trades
4. Sends daily email summary at 2:00 PM
5. Auto-imports portfolio when CSV is dropped

---

### Phase 4: Refinement (Ongoing)

**Weekly Tasks:**
- [ ] Review alert accuracy (false positives?)
- [ ] Tune risk parameters based on performance
- [ ] Adjust AI prompts for better recommendations
- [ ] Add new features (trailing stops, sector rotation)

---

## 11. Database Schemas

### Complete SQLite Schema

```sql
-- File: data/init_schema.sql

-- Portfolio Snapshots (historical portfolio states)
CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_timestamp DATETIME NOT NULL,
    total_equity DECIMAL(15, 2),
    cash_balance DECIMAL(15, 2)
);

-- Holdings (positions in each snapshot)
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    quantity DECIMAL(10, 4),
    cost_basis DECIMAL(10, 4),
    current_value DECIMAL(15, 2),
    FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshot(id)
);

-- Market Data (price cache)
CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    price DECIMAL(10, 4),
    atr DECIMAL(10, 4),
    sma_50 DECIMAL(10, 4),
    is_volatile INTEGER DEFAULT 0,
    source TEXT CHECK(source IN ('Alpaca', 'YFinance', 'Manual'))
);

-- News Analysis (parsed news with sentiment)
CREATE TABLE IF NOT EXISTS news_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    headline TEXT,
    sentiment TEXT CHECK(sentiment IN ('positive', 'negative', 'neutral')),
    confidence DECIMAL(3, 2),
    implied_action TEXT CHECK(implied_action IN ('BUY', 'SELL', 'HOLD')),
    key_reason TEXT,
    urgency TEXT CHECK(urgency IN ('high', 'medium', 'low')),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Strategy Recommendations (AI-generated trade ideas)
CREATE TABLE IF NOT EXISTS strategy_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT CHECK(action IN ('BUY', 'SELL', 'HOLD')),
    confidence DECIMAL(3, 2),
    reasoning TEXT,
    target_price DECIMAL(10, 4),
    stop_loss DECIMAL(10, 4),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Risk Decisions (audit trail of risk controller)
CREATE TABLE IF NOT EXISTS risk_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT,
    approved INTEGER,  -- 1 = approved, 0 = vetoed
    reason TEXT,
    approved_shares INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Trade Log (inferred trades from portfolio diffs)
CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT CHECK(action IN ('BUY', 'SELL')),
    quantity DECIMAL(10, 4),
    snapshot_id INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshot(id)
);

-- Notification Log (audit of all messages sent)
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT CHECK(channel IN ('iMessage', 'email')),
    content TEXT,
    status TEXT,  -- 'sent', 'failed', 'queued'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Stock Metadata (sector, industry for risk checks)
CREATE TABLE IF NOT EXISTS stock_metadata (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    industry TEXT,
    avg_volume_20d INTEGER,
    last_updated DATETIME
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_analysis(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_holdings_snapshot ON holdings(snapshot_id);
```

**Initialize Database:**
```bash
sqlite3 data/agent.db < data/init_schema.sql
```

---

## 12. Configuration & Deployment

### 12.1 Configuration File

**File: `config/config.yaml`**

```yaml
# API Keys (alternatively use environment variables)
api_keys:
  alpaca_api_key: "YOUR_ALPACA_KEY"
  alpaca_secret_key: "YOUR_ALPACA_SECRET"
  gemini_api_key: "YOUR_GEMINI_KEY"
  finnhub_api_key: "YOUR_FINNHUB_KEY"

# Email Configuration
email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 465
  username: "your_email@gmail.com"
  app_password: "YOUR_GMAIL_APP_PASSWORD"
  recipient: "your_email@gmail.com"

# iMessage Configuration
imessage:
  recipient: "+1234567890"  # Your phone number or Apple ID

# Risk Management
risk:
  max_position_size_pct: 0.20      # 20% max per stock
  max_sector_exposure_pct: 0.40    # 40% max per sector
  risk_per_trade_pct: 0.015        # 1.5% portfolio risk per trade
  max_volatility_pct: 0.10         # 10% ATR relative to price
  stop_loss_atr_multiplier: 2.5    # 2.5x ATR for stops

# Schedule Configuration
schedule:
  timezone: "America/Los_Angeles"
  quiet_hours_start: "21:00"  # 9 PM
  quiet_hours_end: "06:00"    # 6 AM
  market_open: "06:30"        # 6:30 AM PT
  market_close: "13:00"       # 1:00 PM PT

# Paths
paths:
  database: "/Users/YOUR_USERNAME/StockAgent/data/agent.db"
  inbox: "/Users/YOUR_USERNAME/StockAgent/inbox"
  logs: "/Users/YOUR_USERNAME/StockAgent/logs"

# Watchlist (symbols to monitor)
watchlist:
  - AAPL
  - MSFT
  - GOOGL
  - AMZN
  - TSLA
  - NVDA
  - META
  - NFLX

# AI Configuration
ai:
  model_strategy: "gemini-1.5-pro"
  model_sentiment: "gemini-1.5-flash"
  temperature_strategy: 0.3
  temperature_sentiment: 0.1
  max_tokens_strategy: 1000
  max_tokens_sentiment: 200
```

**Loading Configuration:**
```python
# File: src/utils/config.py

import yaml

def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)

# Usage
config = load_config()
api_key = config['api_keys']['gemini_api_key']
```

### 12.2 Requirements File

**File: `requirements.txt`**

```text
# Data & APIs
pandas==2.2.0
alpaca-py==0.22.0
yfinance==0.2.36
finnhub-python==2.4.19

# AI
google-generativeai==0.8.3

# Database
# (sqlite3 is built into Python)

# Scheduling & File Watching
watchdog==4.0.0
pytz==2024.1

# Configuration
pyyaml==6.0.1

# Logging
colorlog==6.8.2

# Testing (optional)
pytest==8.0.0
```

**Install:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 12.3 Directory Structure

```
StockAgent/
├── config/
│   └── config.yaml
├── data/
│   ├── agent.db
│   └── init_schema.sql
├── inbox/
│   └── (drop CSV files here)
├── logs/
│   ├── stdout.log
│   ├── stderr.log
│   └── system.log
├── src/
│   ├── agents/
│   │   ├── market_analyst.py
│   │   ├── news_analyst.py
│   │   ├── portfolio_accountant.py
│   │   ├── strategy_planner.py
│   │   ├── risk_controller.py
│   │   └── notification_specialist.py
│   ├── data/
│   │   └── cache_manager.py
│   ├── utils/
│   │   ├── config.py
│   │   └── watchdog_csv.py
│   ├── main_orchestrator.py
│   └── test_phase1.py
├── venv/
├── requirements.txt
└── README.md
```

---

## 13. Evaluation & Continuous Improvement

### 13.1 Performance Metrics

Track these metrics weekly:

| Metric | Formula | Target |
|--------|---------|--------|
| **Win Rate** | `(Winning Trades) / (Total Trades)` | >55% |
| **Profit Factor** | `(Gross Profit) / (Gross Loss)` | >1.5 |
| **Sharpe Ratio** | `(Return - Risk-Free) / Std Dev` | >1.0 |
| **Max Drawdown** | `max(Peak - Trough) / Peak` | <15% |
| **Avg Win/Loss Ratio** | `(Avg Win) / (Avg Loss)` | >1.5 |

**Calculate via SQL:**
```sql
-- Win Rate
SELECT 
    COUNT(CASE WHEN (exit_price - entry_price) > 0 THEN 1 END) * 1.0 / COUNT(*) as win_rate
FROM trade_log
WHERE action = 'SELL'
AND timestamp > date('now', '-30 days');

-- Average Win vs Loss
SELECT 
    AVG(CASE WHEN (exit_price - entry_price) > 0 THEN (exit_price - entry_price) END) as avg_win,
    AVG(CASE WHEN (exit_price - entry_price) < 0 THEN ABS(exit_price - entry_price) END) as avg_loss
FROM trade_log
WHERE action = 'SELL';
```

### 13.2 A/B Testing Framework

**Strategy Variants:**
Run multiple strategy agents in parallel (one active, others in "shadow mode"):

```python
# File: src/agents/strategy_variants.py

class StrategyTrend(StrategyPlanner):
    """Momentum-based strategy"""
    pass

class StrategyMeanReversion(StrategyPlanner):
    """Contrarian strategy"""
    pass

# In main_orchestrator.py
active_strategy = StrategyTrend(...)
shadow_strategy = StrategyMeanReversion(...)

# Generate recommendations from both
rec_active = active_strategy.generate_recommendation('AAPL')
rec_shadow = shadow_strategy.generate_recommendation('AAPL')

# Only notify user with active strategy
notify(rec_active)

# Log shadow strategy for comparison
log_shadow_recommendation(rec_shadow)
```

After 30 days, compare:
- Which strategy had higher win rate?
- Which had better risk-adjusted returns?
- Switch if shadow consistently outperforms.

### 13.3 Feedback Loop

**User Feedback Mechanism:**
After each alert, track:
- Did you execute the trade?
- If not, why? (too risky, disagreed with reasoning, bad timing)

```python
# Add to notification_specialist.py

def log_user_response(recommendation_id: int, response: str):
    """
    Track user's response to recommendations
    response: 'executed', 'skipped_risk', 'skipped_timing', 'disagreed'
    """
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE strategy_recommendations
        SET user_response = ?, response_time = datetime('now')
        WHERE id = ?
    """, (response, recommendation_id))
    
    conn.commit()
    conn.close()
```

**Analysis:**
If you consistently skip recommendations with certain characteristics (e.g., "High volatility" or "Tech sector"), the system can learn to reduce those alerts.

### 13.4 Prompt Tuning

**Iterative Improvement:**
1. Review AI-generated reasoning for bad recommendations
2. Identify which step in Chain-of-Thought failed
3. Refine prompt to emphasize that consideration

**Example:**
- **Problem:** AI recommended buying a stock that had already rallied 50% in a week
- **Root Cause:** Step 1 (technical analysis) didn't check for overextension
- **Fix:** Add to prompt: "In Step 1, explicitly check if the stock is >20% above its 200-day MA, which indicates potential overextension."

### 13.5 Guardrails Against Overfitting

**Rules:**
1. Never hardcode symbol-specific rules (e.g., "always buy AAPL on Mondays")
2. Backtest changes on historical data before deploying
3. Require at least 30 trades before evaluating a strategy change
4. Use out-of-sample testing (train on 2024 data, test on 2025)

---

## Appendices

### Appendix A: Security Best Practices

1. **API Keys:**
   - Store in environment variables or macOS Keychain
   - Never commit to Git
   - Use `.gitignore` for config files

2. **Database:**
   - Encrypt `agent.db` if storing on cloud backup
   - Use `chmod 600` to restrict file permissions

3. **iMessage:**
   - Messages are end-to-end encrypted by Apple
   - No sensitive portfolio details in messages (use codes/references)

### Appendix B: Troubleshooting

**Problem:** launchd job not running
- **Check:** `launchctl list | grep stockagent`
- **View errors:** `cat ~/StockAgent/logs/stderr.log`
- **Common fix:** Incorrect Python path in plist

**Problem:** iMessage not sending
- **Check:** System Settings → Privacy → Automation
- **Grant:** Terminal/Python permission to control Messages
- **Test:** `osascript -e 'tell app "Messages" to send "test" to buddy "your_number"'`

**Problem:** Gemini API rate limit exceeded
- **Cause:** Too many requests per minute
- **Fix:** Increase cache TTL or reduce scan frequency

### Appendix C: Glossary

| Term | Definition |
|------|------------|
| **ATR** | Average True Range - measures volatility |
| **SMA** | Simple Moving Average - trend indicator |
| **Sharpe Ratio** | Risk-adjusted return metric |
| **launchd** | macOS background task scheduler |
| **Chain-of-Thought** | AI prompting technique forcing step-by-step reasoning |
| **Grounding** | Providing factual data to prevent AI hallucination |
| **HITL** | Human-in-the-Loop - system requires human approval |

---

## Conclusion

This consolidated design provides a **buildable, safe, and intelligent** automated trading system tailored to macOS. By combining:

- **Multi-agent architecture** (separation of concerns)
- **Gemini AI integration** (reasoning and sentiment)
- **Rigorous risk management** (mathematical constraints)
- **macOS-native automation** (launchd, AppleScript)
- **Human-in-the-loop control** (you approve all trades)

...you have a system that acts as a tireless analyst while you maintain ultimate authority.

**Next Steps:**
1. Set up development environment
2. Initialize database with schemas
3. Follow Phase 1 implementation (weeks 1-2)
4. Test with paper trading before live capital

**Remember:**
- Markets are unpredictable
- Past performance ≠ future results
- This system is a tool, not a guarantee
- You are responsible for all trading decisions

*Good luck building your automated trading intelligence system!*

---

**Document Version:** 1.0  
**Last Updated:** January 28, 2026  
**Author:** Consolidated from two research documents  
**Status:** Ready for Implementation
