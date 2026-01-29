# Setup Guide: Stock Trading Intelligence System

A step-by-step guide to configure and run the system for the first time.

---

## Helper Scripts

This guide uses helper scripts from the `scripts/` folder to simplify common tasks:

| Script | Purpose |
|--------|---------|
| `scripts/check_config.py` | Verify API keys and environment setup |
| `scripts/import_portfolio.py` | Import Fidelity CSV exports |
| `scripts/test_market_data.py` | Test market data fetching |
| `scripts/test_screener.py` | Test stock screener |
| `scripts/check_database.py` | View database status |
| `scripts/run_system.py` | Run the trading system |

---

## Prerequisites

- macOS 12+
- Python 3.10+
- Terminal access

---

## Step 1: Install Dependencies

```bash
cd /Users/shengpeng/study/repo/my_trading

# Create virtual environment (skip if already done)
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

---

## Step 2: Get API Keys

You need at least **one** API key to get useful results. Here's what each provides:

| API | Purpose | Required? | Free Tier |
|-----|---------|-----------|-----------|
| **Gemini** | AI recommendations | Recommended | Yes (free) |
| **Alpaca** | Stock prices + screening | Optional | Yes (200/min) |
| **Alpha Vantage** | Backup stock screening | Optional | Yes (25/day) |
| **Finnhub** | News data | Optional | Yes (60/min) |

### 2.1 Get Gemini API Key (Recommended)

1. Go to https://aistudio.google.com/apikey
2. Sign in with Google account
3. Click "Create API Key"
4. Copy the key

### 2.2 Get Alpaca API Key (Optional but Recommended)

1. Go to https://alpaca.markets/
2. Sign up for free account
3. Go to Dashboard → Paper Trading → API Keys
4. Generate new key pair
5. Copy both API Key and Secret Key

### 2.3 Get Alpha Vantage API Key (Optional)

1. Go to https://www.alphavantage.co/support/#api-key
2. Enter email to get free key instantly
3. Copy the key (used as backup for stock screening)

### 2.4 Get Finnhub API Key (Optional)

1. Go to https://finnhub.io/
2. Sign up for free account
3. Copy API key from dashboard

---

## Step 3: Configure Environment Variables

Create a `.env` file in the project root:

```bash
cd /Users/shengpeng/study/repo/my_trading

cat > .env << 'EOF'
# Required for AI recommendations
export GEMINI_API_KEY="paste-your-gemini-key-here"

# Optional: Market data + stock screening
export ALPACA_API_KEY="paste-your-alpaca-key-here"
export ALPACA_SECRET_KEY="paste-your-alpaca-secret-here"

# Optional: Backup stock screening (25 calls/day free)
export ALPHA_VANTAGE_API_KEY="paste-your-alpha-vantage-key-here"

# Optional: News analysis
export FINNHUB_API_KEY="paste-your-finnhub-key-here"

# Optional: Email notifications
export GMAIL_USER="your-email@gmail.com"
export GMAIL_APP_PASSWORD="your-app-password"
export EMAIL_RECIPIENT="your-email@gmail.com"

# Optional: iMessage notifications (phone number or Apple ID)
export IMESSAGE_RECIPIENT="+1234567890"
EOF
```

**Important:** Replace the placeholder values with your actual keys!

Load the environment:
```bash
source .env
```

---

## Step 4: Initialize Database

```bash
source venv/bin/activate
sqlite3 data/agent.db < data/init_schema.sql
```

This creates all required tables. Safe to run multiple times.

---

## Step 5: Prepare Your Portfolio CSV

The system reads Fidelity CSV exports. You have two options:

### Option A: Use Sample Data (for testing)

A sample file already exists at `inbox/sample_portfolio.csv`:
```
AAPL: 50 shares @ $170 cost basis
MSFT: 20 shares @ $360 cost basis
NVDA: 10 shares @ $400 cost basis
Cash: $3,500
```

### Option B: Export from Fidelity (for real use)

1. Log into Fidelity.com
2. Go to Accounts → Positions
3. Click "Download" → CSV
4. Save file to `inbox/` folder

**CSV Format Expected:**
```csv
Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Cost Basis Per Share,Unrealized Gain/Loss,Unrealized Gain/Loss %,Type
Z12345678,Individual,AAPL,APPLE INC,50,178.45,8922.50,8500.00,170.00,422.50,4.97,Cash
Z12345678,Individual,SPAXX,FIDELITY GOVERNMENT MONEY MARKET,3500.00,1.00,3500.00,3500.00,1.00,0.00,0.00,Cash
```

---

## Step 6: Import Portfolio

```bash
source venv/bin/activate
source .env

# Import the most recent CSV from inbox/
python scripts/import_portfolio.py

# Or specify a file:
python scripts/import_portfolio.py inbox/sample_portfolio.csv
```

Expected output:
```
📄 Using most recent CSV: my_portfolio.csv

📥 Importing: inbox/my_portfolio.csv
--------------------------------------------------

✅ Import successful! Snapshot #1

==================================================
                PORTFOLIO SUMMARY
==================================================
  Total Equity:  $        10,000.00
  Cash Balance:  $        10,000.00
  Invested:      $             0.00
  Positions:                     0
==================================================
```

---

## Step 7: Verify Configuration

```bash
source venv/bin/activate
source .env

python scripts/check_config.py
```

This checks all API keys, config files, database, and inbox folder status.

---

## Step 8: Test Market Data Fetch

```bash
source venv/bin/activate
source .env

# Test with default symbols (AAPL, MSFT, GOOGL)
python scripts/test_market_data.py

# Or specify your own symbols
python scripts/test_market_data.py TSLA NVDA AMD
```

Expected output:
```
============================================================
Market Data Test
============================================================
📡 Data source: Alpaca API (with Yahoo Finance fallback)
🔍 Testing symbols: AAPL, MSFT, GOOGL
------------------------------------------------------------

Fetching market data...

Symbol      Price      ATR     SMA-50       Volume Volatile Source
----------------------------------------------------------------------
AAPL      $227.63     3.82   $233.49    48,123,456       No Alpaca
MSFT      $442.15     6.21   $428.92    18,234,567       No Alpaca
GOOGL     $197.84     4.15   $178.23    22,456,789       No Alpaca
----------------------------------------------------------------------

✅ Fetched data for 3/3 symbols
```

---

## Step 9: Run the System

```bash
source venv/bin/activate
source .env

# Pre-market mode (safe - just scans and analyzes)
python scripts/run_system.py premarket

# Market mode (generates recommendations)
python scripts/run_system.py market

# Post-market mode (daily summary)
python scripts/run_system.py postmarket

# Auto-detect based on time of day
python scripts/run_system.py
```

This automatically selects mode based on current time (Pacific):
- 6:00-6:30 AM: Pre-market
- 6:30 AM-1:00 PM: Market hours
- 1:00-2:00 PM: Post-market
- Other times: Closed (no action)

---

## Step 10: View Results

### Quick Status Check

```bash
python scripts/check_database.py
```

This shows portfolio, recommendations, risk decisions, screener results, and news analysis.

### Detailed View

```bash
python scripts/check_database.py --full
```

### Test Stock Screener

```bash
python scripts/test_screener.py

# Or limit results
python scripts/test_screener.py --max 5
```

### Raw SQL Queries (Optional)

```bash
# Check recommendations
sqlite3 data/agent.db "SELECT symbol, action, confidence FROM strategy_recommendations ORDER BY timestamp DESC LIMIT 5;"

# Check risk decisions
sqlite3 data/agent.db "SELECT symbol, action, approved, reason FROM risk_decisions ORDER BY timestamp DESC LIMIT 5;"

# Check screened stocks
sqlite3 data/agent.db "SELECT symbol, source, rank FROM screener_results ORDER BY rank LIMIT 10;"
```

---

## Ongoing Usage

### Daily Workflow

1. **Morning (before market):** Export Fidelity CSV → drop in `inbox/`
2. **System auto-discovers tradeable stocks** via Alpaca movers + Alpha Vantage
3. **System runs automatically** (if launchd configured) or manually:
   ```bash
   source venv/bin/activate && source .env
   python src/main_orchestrator.py
   ```
4. **Receive alerts** via iMessage/email for trade recommendations
5. **You decide** whether to execute trades (system never trades automatically)

### Auto-Import CSVs (Optional)

Run the watchdog to auto-import CSVs when dropped in inbox:

```bash
source venv/bin/activate
python src/utils/watchdog_csv.py
```

### Schedule with launchd (Optional)

See `launchd/com.user.stockagent.plist` for automatic scheduling.

---

## Troubleshooting

### "No data available" for symbols
- Yahoo Finance may be rate-limited (wait 10 min)
- Or set up Alpaca API keys for reliable data

### "Gemini API error"
- Check your API key is correct
- Verify at https://aistudio.google.com/apikey

### "iMessage not sending"
- Grant Terminal access: System Settings → Privacy → Automation → Terminal → Messages

### Database errors
- Re-initialize: `sqlite3 data/agent.db < data/init_schema.sql`

---

## Quick Reference

```bash
# Always start with
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate
source .env

# Check configuration
python scripts/check_config.py

# Import portfolio
python scripts/import_portfolio.py                 # Latest from inbox/
python scripts/import_portfolio.py inbox/file.csv  # Specific file

# Test market data
python scripts/test_market_data.py                 # Default symbols
python scripts/test_market_data.py TSLA NVDA       # Custom symbols

# Test stock screener
python scripts/test_screener.py                    # Find tradeable stocks
python scripts/test_screener.py --max 5            # Limit results

# Run trading system
python scripts/run_system.py premarket             # Safe test
python scripts/run_system.py market                # Get recommendations
python scripts/run_system.py postmarket            # Daily summary
python scripts/run_system.py                       # Auto-detect mode

# Check database status
python scripts/check_database.py                   # Quick status
python scripts/check_database.py --full            # Detailed view

# Run tests
python -m pytest tests/ -v
```
