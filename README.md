# Automated Stock Trading Intelligence System

A locally-run, multi-agent AI-powered trading analysis system for macOS. Provides intelligent trade recommendations with human-in-the-loop approval via iMessage and email notifications.

> **⚠️ Disclaimer**: This system provides recommendations only—it does not execute trades automatically. Always verify recommendations before taking action.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Testing](#testing)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features
 
 - **Web Dashboard**: Server-rendered UI with GitHub OAuth, portfolio views, and orchestrator controls
 - **Portfolio CSV Upload**: Drag-and-drop Fidelity CSV import via web browser
 - **Real-Time Run Logs**: Live progress display during orchestrator runs
 - **Smart Mode Suggestions**: Time-based recommendations (premarket/market/postmarket) with confirmation dialogs
 - **Chat Interface**: Conversational trade advisor for natural language questions
 - **Rest API**: High-performance FastAPI backend with secure API Key authentication
 - **Cloud Database**: Turso (libSQL) integration for cross-device data access
 - **Dynamic Stock Discovery**: Automatic screening via Alpaca/Alpha Vantage + **LLM Re-ranking**
 - **Portfolio Tracking**: Automatic import of Fidelity CSVs with trade inference via state diffing
 - **Market Analysis**: Real-time price fetching with technical indicators (ATR, SMA)
 - **AI-Powered Insights**: Gemini AI for news sentiment, strategy recommendations, and **screener ranking**
 - **Trade Question Advisor**: Natural language Q&A about your portfolio and trades ("Should I sell MSFT at 480?")
 - **Risk Management**: Deterministic position sizing, volatility filters, and sector exposure limits
 - **Smart Notifications**: iMessage for urgent alerts, email for daily summaries
 - **macOS Automation**: `launchd` scheduling and file system watchdog for automatic imports
 
 ---
 
 ## Architecture
 
 ```
 ┌─────────────────────────────────────────────────────────────────┐
 │                        ORCHESTRATOR                              │
 │              (Time-based mode: premarket/market/postmarket)      │
 └─────────────────────────────────────────────────────────────────┘
                                  │
    ┌─────────────┬───────────────┼───────────────┬─────────────┐
    ▼             ▼               ▼               ▼             ▼
 ┌────────┐ ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐
 │ Stock  │ │Portfolio │   │  Market  │   │   News   │   │Strategy│
 │Screener│ │Accountant│   │ Analyst  │   │ Analyst  │   │Planner │
 │(AI)    │ │          │   │          │   │          │   │        │
 │• Alpaca│ │• CSV     │   │• Prices  │   │• Finnhub │   │• CoT   │
 │• Gemini│ │• Holdings│   │• ATR/SMA │   │• Gemini  │   │• Recom │
 │• Rank  │ │• Diffing │   │• Volume  │   │• Sentiment│   │• Score │
 └────┬───┘ └────┬─────┘   └────┬─────┘   └────┬─────┘   └───┬────┘
      │          │              │              │             │
      └──────────┴──────────────┼──────────────┴─────────────┘
                                ▼
                     ┌──────────────────┐
                     │  Risk Controller  │
                     │                   │
                     │ • Position Sizing │
                     │ • Exposure Limits │
                     │ • Stop-Loss Calc  │
                     └─────────┬─────────┘
                               ▼
 ┌──────────────┐     ┌────────────────────┐
 │   REST API   │◄────┤Notification Special│
 │  (FastAPI)   │     │                    │
 │ • Portfolio  │     │ • iMessage (urgent)│
 │ • Agents     │     │ • Email (summaries)│
 │ • Market     │     │ • Quiet Hours      │
 └──────┬───────┘     └────────────────────┘
        │
        ▼
 ┌──────────────┐
 │   Database   │
 │ (Turso/Local)│
 └──────────────┘
 ```

### Agent Descriptions

| Agent | Responsibility | AI/Deterministic |
|-------|---------------|------------------|
| **Stock Screener** | Discovers stocks via Alpaca movers, then **re-ranks using Gemini AI** | **AI-Enhanced** |
| **Portfolio Accountant** | Parses Fidelity CSVs, tracks holdings, infers trades | Deterministic |
| **Market Analyst** | Fetches prices, calculates ATR/SMA, detects volatility | Deterministic |
| **News Analyst** | Aggregates news, extracts sentiment via Gemini AI | AI-Powered |
| **Strategy Planner** | Synthesizes data, generates recommendations with CoT reasoning | AI-Powered |
| **Trade Advisor** | Answers natural language questions about trades with context | AI-Powered |
| **Risk Controller** | Enforces position limits, volatility filters, calculates stop-loss | Deterministic |
| **Notification Specialist** | Routes alerts via iMessage/email based on urgency | Deterministic |

### Database Schema

SQLite database with 10 tables:
- `portfolio_snapshot` / `holdings` - Portfolio state
- `market_data` - Price cache with TTL
- `news_analysis` - Sentiment results
- `strategy_recommendations` - AI recommendations
- `risk_decisions` - Approval/veto audit trail
- `trade_log` - Inferred trades
- `notification_log` - Delivery history
- `stock_metadata` - Sector/industry info
- `screener_results` - Cached screening outputs
- `screener_runs` - Screening audit trail

---

## Tech Stack
 
 | Component | Technology |
 |-----------|------------|
 | Language | Python 3.10+ |
 | Database | **Turso (libSQL)** or Local SQLite |
 | API Backend | **FastAPI** + Uvicorn |
 | Market Data | Alpaca API → Yahoo Finance → Alpaca Quotes (fallback chain) |
 | Stock Screening | Alpaca Movers API → Alpha Vantage → **Gemini AI Re-ranking** |
 | News Data | Finnhub API |
 | AI | Google Gemini (gemini-2.5-flash) |
 | Notifications | macOS Messages (AppleScript), Gmail SMTP |
 | Scheduling | macOS launchd or Cloud Cron |
 | File Watching | watchdog library |
 
 ---
 
 ## Prerequisites
 
 - **Python** 3.10 or higher
 - **Turso Account** (for cloud database)
 - **macOS** 12.0+ (optional, for local iMessage)
 - **API Keys** (optional but recommended):
   - [Alpaca](https://alpaca.markets/) - Market data + stock screening
   - [Alpha Vantage](https://www.alphavantage.co/) - Backup screener (free: 25/day)
   - [Finnhub](https://finnhub.io/) - News aggregation
   - [Google Gemini](https://ai.google.dev/) - AI analysis
   - Gmail App Password - Email notifications
 
 ---
 
 ## Installation
 
 ### 1. Clone the Repository
 
 ```bash
 git clone https://github.com/yourusername/my_trading.git
 cd my_trading
 ```
 
 ### 2. Create Virtual Environment
 
 ```bash
 python3 -m venv venv
 source venv/bin/activate
 ```
 
 ### 3. Install Dependencies
 
 ```bash
 pip install -r requirements.txt
 ```
 
 **Core dependencies:**
 ```
 pandas>=2.0.0          # Data manipulation
 fastapi>=0.109.0       # REST API
 uvicorn[standard]      # ASGI Server
 libsql-experimental    # Turso Database client
 google-generativeai    # Gemini AI
 alpaca-py>=0.10.0      # Market data API
 watchdog>=3.0.0        # File system monitoring
 ```
 
 ### 4. Initialize Database
 
 See [doc/cloud_migration_guide.md](doc/cloud_migration_guide.md) for full Turso setup.
 
 For local-only mode:
 ```bash
 sqlite3 data/agent.db < data/init_schema.sql
 ```
 
 ---
 
 ## Configuration
 
 ### 1. Set Environment Variables
 
 Add to your `~/.zshrc` or `.env` file:
 
 ```bash
 # Security (Required for API)
 export API_KEY="your-secure-random-key"
 
 # Database (Turso Cloud or Local)
 export DB_MODE="turso"  # or 'local'
 export TURSO_DATABASE_URL="libsql://your-db.turso.io"
 export TURSO_AUTH_TOKEN="your-turso-token"
 
 # Required for AI features
 export GEMINI_API_KEY="your_gemini_api_key"
 
 # Optional: Market data + stock screening
 export ALPACA_API_KEY="your_alpaca_key"
 export ALPACA_SECRET_KEY="your_alpaca_secret"
 
 # Optional: Backup stock screener (25 calls/day free)
 export ALPHA_VANTAGE_API_KEY="your_alpha_vantage_key"
 
 # Optional: News aggregation
 export FINNHUB_API_KEY="your_finnhub_key"
 
 # Optional: Email notifications
 export GMAIL_USER="your_email@gmail.com"
 export GMAIL_APP_PASSWORD="your_app_password"
 export EMAIL_RECIPIENT="your_email@gmail.com"
 
 # Optional: iMessage
 export IMESSAGE_RECIPIENT="+1234567890"
 ```
 
 Reload your shell:
 ```bash
 source ~/.zshrc
 ```

### 2. Configure `config/config.yaml`

The config file uses environment variable substitution. Key settings:

```yaml
# API Keys (from environment)
api_keys:
  alpaca_api_key: "${ALPACA_API_KEY}"
  gemini_api_key: "${GEMINI_API_KEY}"
  alpha_vantage_api_key: "${ALPHA_VANTAGE_API_KEY}"

# Risk Parameters (adjust to your risk tolerance)
risk:
  max_position_size_pct: 0.20    # Max 20% in single stock
  max_sector_exposure_pct: 0.40  # Max 40% in single sector
  risk_per_trade_pct: 0.015      # Risk 1.5% per trade
  stop_loss_atr_multiplier: 2.5  # Stop at 2.5x ATR

# Stock Screener (dynamic stock discovery)
screener:
  enabled: true                  # Enable dynamic screening
  max_screened_symbols: 10       # Max symbols to add
  cache_ttl_seconds: 3600        # 1-hour cache
  
  # LLM Re-ranking (intelligent ranking)
  use_llm_ranking: true          # Enable AI analysis
  llm_candidate_pool: 10         # Stocks to analyze
  model_screening: "gemini-2.5-flash"

# Watchlist (always monitored, in addition to screened stocks)
watchlist:
  - AAPL
  - MSFT
  - GOOGL
  - NVDA

# Schedule (Pacific Time)
schedule:
  timezone: "America/Los_Angeles"
  market_open: "06:30"
  market_close: "13:00"
  quiet_hours_start: "21:00"
  quiet_hours_end: "06:00"
```

### 3. Grant iMessage Permissions

For iMessage to work, Terminal (or your IDE) needs permission:

1. Open **System Preferences** → **Security & Privacy** → **Privacy**
2. Select **Automation**
3. Enable **Terminal** → **Messages**

---

## Running the System

### Manual Execution

```bash
# Activate virtual environment
source venv/bin/activate

# Run with auto-detected mode
python src/main_orchestrator.py

# Force specific mode
python src/main_orchestrator.py --mode premarket
python src/main_orchestrator.py --mode market
python src/main_orchestrator.py --mode postmarket
```

### Scheduled Execution (launchd)

1. **Edit the plist** - Replace `YOUR_USERNAME` in `launchd/com.user.stockagent.plist`:

```xml
<string>/Users/YOUR_USERNAME/study/repo/my_trading/venv/bin/python3</string>
```

2. **Install the job**:

```bash
cp launchd/com.user.stockagent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.stockagent.plist
```

3. **Verify it's loaded**:

```bash
launchctl list | grep stockagent
```

4. **Unload if needed**:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.stockagent.plist
```

### CSV File Watchdog

Start the watchdog to auto-import Fidelity CSVs:

```bash
python src/utils/watchdog_csv.py
```

Drop CSV files into `inbox/` folder and they'll be imported automatically.

### Trade Question Advisor
 
 Ask natural language questions about your portfolio:
 
 ```bash
 # Single question
 python scripts/ask_trade.py "Should I sell 100 shares of MSFT at 480?"
 
 # Interactive mode
 python scripts/ask_trade.py --interactive
 ```
 
 The advisor uses your portfolio data, recent news, market data, and past recommendations to provide AI-powered suggestions with confidence levels.
 
 ---
 
 ## REST API Usage
 
 The system provides a FastAPI-based REST API for programmatic access.
 
 ### Start the Server
 
 ```bash
 uvicorn src.api.main:app --reload --port 8000
 ```
 
 ### Authentication
 
 All endpoints require the `X-API-Key` header with the key defined in your environment.
 
 ### Example Endpoints
 
 | Endpoint | Method | Description |
 |----------|--------|-------------|
 | `/health` | GET | System status (Public) |
 | `/portfolio/summary` | GET | Current holdings and value |
 | `/market/prices/{symbol}` | GET | Real-time price and indicators |
 | `/agent/ask` | POST | Ask the Trade Advisor a question |
 
 ### Example Request
 
 ```bash
 curl -H "X-API-Key: your-secure-key" http://localhost:8000/portfolio/summary
 ```

---

## Web Dashboard

The system includes a server-rendered web dashboard with GitHub OAuth authentication.

### Start the Dashboard

```bash
# Set required environment variables
export SESSION_SECRET="your-session-secret"
export GITHUB_CLIENT_ID="your-github-client-id"
export GITHUB_CLIENT_SECRET="your-github-client-secret"
export GITHUB_ALLOWED_USERS="username1,username2"

# Start the server
uvicorn src.api.main:app --reload --port 8000
```

Then visit: http://localhost:8000/

### Dashboard Pages

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Portfolio summary + orchestrator controls |
| Portfolio | `/portfolio` | Full holdings view |
| Recommendations | `/recommendations` | Trade recommendations with filters |
| Chat | `/chat` | Trade advisor chat interface |

### Chat Interface

The `/chat` page provides a conversational interface to the Trade Advisor:

- Ask questions like "Should I buy AAPL?" or "What's your view on MSFT?"
- Responses include recommendation, confidence level, and reasoning
- Requires GitHub login

### On-Demand Orchestrator Runs

From the dashboard home page, logged-in users can trigger:
- **Premarket Scan** - Run before market opens
- **Market Analysis** - Run during market hours
- **Postmarket Summary** - Run after market closes

Status updates poll automatically until completion.
 
 ---
 
 ## Testing
 
 ### Run All Tests
 
 ```bash
 source venv/bin/activate
 python -m pytest tests/ -v
 ```
 
 ### Run Specific Test Files
 
 ```bash
 # API Tests
 python -m pytest tests/test_api.py -v
 
 # Portfolio Accountant tests
 python -m pytest tests/test_portfolio_accountant.py -v
 ```
 
 ### Integration Test
 
 ```bash
 python src/test_phase1.py
 ```
 
 This test:
 1. Initializes the database
 2. Imports sample portfolio CSV
 3. Fetches live market data
 4. Displays portfolio with current prices
 
 Expected output:
 ```
 ============================================================
          PORTFOLIO SNAPSHOT
 ============================================================
 
 Symbol     Shares        Price          Value     Change
 ------------------------------------------------------------
 AAPL           50 $    256.44 $   12,822.00  +3,899.50
 MSFT           20 $    481.63 $    9,632.60  +2,028.60
 ...
 ✅ Phase 1 Integration Test Completed Successfully!
 ```
 
 ---
 
 ## Deployment on Railway
 
 This project is ready for one-click deployment on Railway, but requires **manual configuration** of the start command because `railway.toml` is unlocked to support multiple services (Web + Cron).
 
 ### 1. Web Service (Dashboard)
 When you deploy the repo, you **MUST** set the **Custom Start Command** in Railway Settings -> Deploy:
 
 ```bash
 uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
 ```
 
 ### 2. Cron Jobs (Optional)
 To run automated premarket/market scans, create a **second service** from the same repo and use:
 
 ```bash
 python src/main_orchestrator.py --mode auto
 ```
 
 See [doc/RAILWAY_CRON_SETUP.md](doc/RAILWAY_CRON_SETUP.md) for full cron instructions.
 
 ---
 
 ## Maintenance
 
 ### Daily Tasks
 
 - **Check logs**: `tail -f logs/stdout.log`
 - **Review notifications**: Check iMessage/email for alerts
 - **Update portfolio**: Export CSV from Fidelity → drop in `inbox/`
 
 ### Weekly Tasks

 - **Clean old cache**: Remove market data older than 7 days
   ```bash
   # Turso (cloud)
   turso db shell samtrading "DELETE FROM market_data WHERE timestamp < datetime('now', '-7 days')"

   # Local SQLite
   sqlite3 data/agent.db "DELETE FROM market_data WHERE timestamp < datetime('now', '-7 days')"
   ```
 - **Review risk decisions**: Check vetoed trades
   ```bash
   # Turso (cloud)
   turso db shell samtrading "SELECT * FROM risk_decisions WHERE approved = 0 ORDER BY timestamp DESC LIMIT 10"

   # Local SQLite
   sqlite3 data/agent.db "SELECT * FROM risk_decisions WHERE approved = 0 ORDER BY timestamp DESC LIMIT 10"
   ```
 
 ### Monthly Tasks
 
 - **Update dependencies**:
   ```bash
   pip install --upgrade -r requirements.txt
   ```
 - **Backup database**:
   ```bash
   # Local Mode
   cp data/agent.db data/backups/agent_$(date +%Y%m%d).db
   
   # Turso Mode
   turso db shell trading-system ".dump" > data/backups/turso_$(date +%Y%m%d).sql
   ```
 - **Review performance metrics** in `strategy_recommendations` table
 
 ### Log Rotation
 
 Add to crontab for weekly log rotation:
 ```bash
 0 0 * * 0 mv ~/study/repo/my_trading/logs/stdout.log ~/study/repo/my_trading/logs/stdout.$(date +\%Y\%m\%d).log
 ```
 
 ---
 
 ## Troubleshooting
 
 ### Common Issues
 
 | Issue | Solution |
 |-------|----------|
 | "alpaca-py not installed" | Install with `pip install alpaca-py` or use yfinance fallback |
 | "Gemini not configured" | Set `GEMINI_API_KEY` environment variable |
 | "Finnhub API error: 401" | Check `FINNHUB_API_KEY` is valid |
 | iMessage not sending | Grant Terminal automation permissions in System Preferences |
 | "No market data" | Markets may be closed; data fetches during market hours |
 | Database locked | Close other SQLite connections; use WAL mode |
 | "Missing API Key" | Set `API_KEY` env var for REST API usage |
 
 ### Enable Debug Logging
 
 ```python
 import logging
 logging.basicConfig(level=logging.DEBUG)
 ```
 
 ### Check Database State

 **Option A: REST API (recommended)**
 ```bash
 curl -H "X-API-Key: your-key" http://localhost:8000/portfolio/summary
 curl -H "X-API-Key: your-key" http://localhost:8000/agent/recommendations
 ```

 **Option B: Turso CLI (cloud)**
 ```bash
 turso db shell samtrading "SELECT * FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 5"
 ```

 **Option C: SQLite (local only)**
 ```bash
 sqlite3 data/agent.db "SELECT * FROM portfolio_snapshot ORDER BY import_timestamp DESC LIMIT 5"
 sqlite3 data/agent.db "SELECT symbol, price, timestamp FROM market_data ORDER BY timestamp DESC LIMIT 10"
 ```
 
 ### Reset Database
 
 ```bash
 rm data/agent.db
 sqlite3 data/agent.db < data/init_schema.sql
 ```
 
 ---
 
 ## Project Structure
 
 ```
 my_trading/
 ├── config/
 │   └── config.yaml           # Main configuration
 ├── data/
 │   ├── init_schema.sql       # Database schema
 │   └── agent.db              # SQLite database (created at runtime)
 ├── doc/
 │   ├── cloud_migration_guide.md # Full guide for Cloud/API setup
 │   └── SETUP_GUIDE.md        # Original setup guide
 ├── inbox/                    # Drop Fidelity CSVs here
 │   └── sample_portfolio.csv  # Sample file for testing
 ├── launchd/
 │   └── com.user.stockagent.plist  # macOS scheduler config
 ├── logs/                     # Log output directory
 ├── scripts/                  # Helper scripts for common tasks
 │   ├── ask_trade.py          # Trade question advisor CLI
 │   ├── check_config.py       # Verify configuration
 │   ├── check_database.py     # View database status
 │   ├── import_portfolio.py   # Import Fidelity CSVs
 │   ├── run_system.py         # Run trading system
 │   ├── test_market_data.py   # Test market data fetching
 │   └── test_screener.py      # Test stock screener
 ├── src/
 │   ├── agents/               # Logic Agents
 │   │   ├── stock_screener.py
 │   │   ├── portfolio_accountant.py
 │   │   ├── market_analyst.py
 │   │   ├── news_analyst.py
 │   │   ├── strategy_planner.py
 │   │   ├── trade_advisor.py
 │   │   ├── risk_controller.py
 │   │   └── notification_specialist.py
 │   ├── api/                  # REST API
 │   │   ├── routers/          # API Endpoints
 │   │   │   ├── agent.py
 │   │   │   ├── auth.py
 │   │   │   ├── market.py
 │   │   │   ├── orchestrator.py  # On-demand runs API
 │   │   │   └── portfolio.py
 │   │   ├── auth.py           # GitHub OAuth
 │   │   ├── dependencies.py
 │   │   └── main.py
 │   ├── dashboard/            # Web Dashboard
 │   │   ├── routes.py         # Dashboard routes
 │   │   ├── static/css/       # Stylesheets
 │   │   └── templates/        # Jinja2 HTML templates
 │   ├── data/
 │   │   ├── cache_manager.py
 │   │   └── db_connection.py  # Turso/SQLite adapter
 │   ├── utils/
 │   │   ├── config.py
 │   │   └── watchdog_csv.py
 │   ├── main_orchestrator.py  # Main entry point
 │   └── test_phase1.py        # Integration test
 ├── tests/
 │   ├── test_api.py           # API Tests
 │   ├── test_portfolio_accountant.py
 │   └── test_risk_controller.py
 ├── requirements.txt
 └── README.md
 ```
 
 ---
 
 ## License
 
 This project is for personal use. Not financial advice. Use at your own risk.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/ -v`
4. Submit a pull request

---

## Acknowledgments

- [Alpaca Markets](https://alpaca.markets/) for market data API
- [Google Gemini](https://ai.google.dev/) for AI capabilities
- [Finnhub](https://finnhub.io/) for news aggregation
- [yfinance](https://github.com/ranaroussi/yfinance) for free market data fallback
