# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated Stock Trading Intelligence System - a locally-run, multi-agent AI-powered trading analysis system for macOS. The system provides trade recommendations with human-in-the-loop approval via iMessage and email notifications. It never executes trades automatically; users approve all actions.

**Platform**: macOS 12+ (requires AppleScript for iMessage)
**Language**: Python 3.10+
**Database**: SQLite (local) or Turso (cloud) - configurable via `DB_MODE`

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

# Helper scripts (in scripts/ folder)
python scripts/check_config.py       # Verify API keys and setup
python scripts/import_portfolio.py   # Import Fidelity CSV
python scripts/test_market_data.py   # Test price fetching
python scripts/test_screener.py      # Test stock screener + LLM ranking
python scripts/check_database.py     # View database status
python scripts/run_system.py         # Run trading system
python scripts/test_phase1_db.py     # Test database connection (local/Turso)
python scripts/migrate_to_turso.py   # Migrate local DB to Turso cloud

# REST API
uvicorn src.api.main:app --port 8000  # Start API server
open http://localhost:8000/docs       # Interactive API docs
```

## Architecture

### Multi-Agent Pipeline

The system uses a 7-agent architecture with clear separation between deterministic and AI-powered components:

**Data Collection Stage** (all deterministic):
1. **PortfolioAccountant** (`src/agents/portfolio_accountant.py`) - Parses Fidelity CSV exports, creates portfolio snapshots, infers trades via state diffing
2. **MarketAnalyst** (`src/agents/market_analyst.py`) - Fetches prices (Alpaca bars → yfinance → Alpaca quotes fallback), calculates ATR and SMA-50, auto-populates stock metadata
3. **NewsAnalyst** (`src/agents/news_analyst.py`) - Aggregates Finnhub news, AI-powered sentiment analysis (Gemini)
4. **StockScreener** (`src/agents/stock_screener.py`) - Discovers tradeable stocks dynamically using Alpaca movers API + Alpha Vantage fallback, with optional LLM re-ranking via Gemini

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
- **Flexible Storage**: Supports local SQLite (default) or Turso cloud database for cross-device access

## Environment Setup

Create `.env` file in project root (python-dotenv format, no `export`):
```bash
# API Keys
GEMINI_API_KEY=your-key              # Required for AI
ALPACA_API_KEY=your-key              # Optional (falls back to yfinance)
ALPACA_SECRET_KEY=your-key
FINNHUB_API_KEY=your-key             # Optional (for news)
ALPHA_VANTAGE_API_KEY=your-key       # Optional (backup for screener)

# Database Mode (optional - defaults to local)
DB_MODE=local                        # 'local' for SQLite, 'turso' for cloud
TURSO_DATABASE_URL=libsql://...      # Required if DB_MODE=turso
TURSO_AUTH_TOKEN=your-token          # Required if DB_MODE=turso
```

The `.env` file is loaded automatically by python-dotenv.

## Configuration

**`config/config.yaml`** - Main config with environment variable substitution (`${VAR_NAME}` syntax)

Key settings:
- `risk.max_position_size_pct`: 20% max per stock
- `risk.max_sector_exposure_pct`: 40% max per sector
- `risk.min_liquidity_volume`: 200k shares minimum average daily volume
- `schedule.timezone`: Pacific Time default
- `ai.model_strategy`: gemini-2.5-flash
- `ai.model_sentiment`: gemini-2.5-flash
- `limits.max_news_articles`: 5 articles per symbol
- `limits.market_data_ttl_seconds`: 300 (5 min cache)
- `screener.enabled`: true (dynamic stock discovery)
- `screener.max_screened_symbols`: 10 symbols from screening
- `screener.use_llm_ranking`: true (AI-powered re-ranking)

## Database

**`src/data/db_connection.py`** - Database connection adapter supporting:
- **Local mode** (`DB_MODE=local`): Uses `data/agent.db` SQLite file
- **Cloud mode** (`DB_MODE=turso`): Uses Turso cloud SQLite

All agents use `get_connection()` context manager for database access.

**`data/init_schema.sql`** - Schema with 12 tables:
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

## REST API

**`src/api/main.py`** - FastAPI server with API key authentication

Endpoints (all require `X-API-Key` header except `/health`):
- `GET /health` - Health check
- `GET /portfolio/summary` - Portfolio equity and cash
- `GET /portfolio/holdings` - Current holdings list
- `GET /market/price/{symbol}` - Get latest price
- `GET /agent/recommendations` - Recent strategy recommendations
- `POST /agent/ask` - Ask trade advisor (natural language)

Start server: `uvicorn src.api.main:app --port 8000`
API docs: http://localhost:8000/docs

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
