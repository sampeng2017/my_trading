# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated Stock Trading Intelligence System - a locally-run, multi-agent AI-powered trading analysis system for macOS. The system provides trade recommendations with human-in-the-loop approval via iMessage and email notifications. It never executes trades automatically; users approve all actions.

**Platform**: macOS 12+ (requires AppleScript for iMessage)
**Language**: Python 3.10+

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
sqlite3 data/agent.db < data/init_schema.sql

# Run the main orchestrator (auto-detects time mode)
python src/main_orchestrator.py

# Force a specific mode
python src/main_orchestrator.py --mode premarket
python src/main_orchestrator.py --mode market
python src/main_orchestrator.py --mode postmarket

# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_portfolio_accountant.py -v

# Run integration test (auto-initializes database)
python src/test_phase1.py

# CSV watchdog (auto-import Fidelity CSVs from inbox/)
python src/utils/watchdog_csv.py
```

## Architecture

### Multi-Agent Pipeline

The system uses a 7-agent architecture with clear separation between deterministic and AI-powered components:

**Data Collection Stage** (all deterministic):
1. **PortfolioAccountant** (`src/agents/portfolio_accountant.py`) - Parses Fidelity CSV exports, creates portfolio snapshots, infers trades via state diffing
2. **MarketAnalyst** (`src/agents/market_analyst.py`) - Fetches prices (Alpaca bars → yfinance → Alpaca quotes fallback), calculates ATR and SMA-50, auto-populates stock metadata
3. **NewsAnalyst** (`src/agents/news_analyst.py`) - Aggregates Finnhub news, AI-powered sentiment analysis (Gemini)
4. **StockScreener** (`src/agents/stock_screener.py`) - Discovers tradeable stocks dynamically using Alpaca movers API + Alpha Vantage fallback

**Analysis Stage** (AI-powered):
5. **StrategyPlanner** (`src/agents/strategy_planner.py`) - Synthesizes all inputs using Chain-of-Thought prompting, generates BUY/SELL/HOLD recommendations (Gemini Pro)

**Risk & Notification Stage** (deterministic):
6. **RiskController** (`src/agents/risk_controller.py`) - Enforces hard constraints: cash availability, position size limits (20%), sector exposure caps (40%), volatility filters, liquidity requirements
7. **NotificationSpecialist** (`src/agents/notification_specialist.py`) - Routes alerts via iMessage (urgent) or email (summaries), respects quiet hours

### Main Entry Point

**`src/main_orchestrator.py`** - Coordinates all agents with time-based mode detection:
- `premarket`: 6:00-6:30 AM Pacific
- `market`: 6:30 AM-1:00 PM Pacific
- `postmarket`: 1:00-2:00 PM Pacific
- `closed`: outside hours

### Key Design Principles

- **Deterministic Safety + Probabilistic Reasoning**: AI agents provide market interpretation; RiskController enforces mathematical constraints with no AI involvement
- **Fallback Design**: Alpaca bars → yfinance → Alpaca quotes for prices; system gracefully degrades without API keys
- **Local-First**: All data stays local in SQLite; no cloud storage

## Environment Setup

Create `.env` file in project root with API keys:
```bash
export GEMINI_API_KEY="your-key"         # Required for AI
export ALPACA_API_KEY="your-key"         # Optional (falls back to yfinance)
export ALPACA_SECRET_KEY="your-key"
export FINNHUB_API_KEY="your-key"        # Optional (for news)
export ALPHA_VANTAGE_API_KEY="your-key"  # Optional (backup for screener)
```

Load before running: `source .env`

## Configuration

**`config/config.yaml`** - Main config with environment variable substitution (`${VAR_NAME}` syntax)

Key settings:
- `risk.max_position_size_pct`: 20% max per stock
- `risk.max_sector_exposure_pct`: 40% max per sector
- `risk.min_liquidity_volume`: 200k shares minimum average daily volume
- `schedule.timezone`: Pacific Time default
- `ai.model_strategy`: gemini-2.0-flash
- `ai.model_sentiment`: gemini-2.0-flash
- `limits.max_news_articles`: 5 articles per symbol
- `limits.market_data_ttl_seconds`: 300 (5 min cache)
- `screener.enabled`: true (dynamic stock discovery)
- `screener.max_screened_symbols`: 10 symbols from screening

## Database

**`data/init_schema.sql`** - SQLite schema with 10 tables:
- `portfolio_snapshot` / `holdings`: Portfolio state
- `market_data`: Price cache with TTL
- `news_analysis`: Sentiment results
- `strategy_recommendations`: AI trade recommendations
- `risk_decisions`: Approval/veto audit trail
- `trade_log`: Inferred trades from portfolio diffs
- `notification_log`: Delivery history
- `stock_metadata`: Sector/industry info
- `screener_results`: Cached screening outputs
- `screener_runs`: Screening audit trail

## Workflow

1. Drop Fidelity CSV exports into `inbox/` folder (or use watchdog for auto-import)
2. PortfolioAccountant imports and snapshots holdings
3. StockScreener discovers additional tradeable stocks (Alpaca movers → Alpha Vantage fallback)
4. MarketAnalyst fetches current prices and indicators for all symbols
5. NewsAnalyst gathers and analyzes relevant news
6. StrategyPlanner synthesizes data into recommendations
7. RiskController validates against constraints
8. NotificationSpecialist alerts user for approval
9. User manually executes approved trades
