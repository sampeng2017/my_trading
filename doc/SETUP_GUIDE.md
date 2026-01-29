# Setup Guide: Stock Trading Intelligence System

A step-by-step guide to configure and run the system for the first time.

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

python -c "
from src.agents.portfolio_accountant import PortfolioAccountant
pa = PortfolioAccountant('data/agent.db')
snapshot_id = pa.import_fidelity_csv('inbox/sample_portfolio.csv')
snapshot = pa.get_latest_snapshot()
print(f'Imported snapshot #{snapshot_id}')
print(f'Total Equity: \${snapshot[\"total_equity\"]:,.2f}')
print(f'Cash: \${snapshot[\"cash_balance\"]:,.2f}')
print(f'Holdings: {len(snapshot[\"holdings\"])}')
for h in snapshot['holdings']:
    print(f'  {h[\"symbol\"]}: {h[\"quantity\"]} shares')
"
```

---

## Step 7: Verify Configuration

Run this to check what's configured:

```bash
source venv/bin/activate
source .env

python -c "
import os

print('=== API Keys Status ===')
print(f'GEMINI_API_KEY:       {\"✅ Set\" if os.getenv(\"GEMINI_API_KEY\") else \"❌ Not set\"}')
print(f'ALPACA_API_KEY:       {\"✅ Set\" if os.getenv(\"ALPACA_API_KEY\") else \"❌ Not set (will use Yahoo)\"}')
print(f'ALPHA_VANTAGE_KEY:    {\"✅ Set\" if os.getenv(\"ALPHA_VANTAGE_API_KEY\") else \"❌ Not set (screener backup)\"}')
print(f'FINNHUB_API_KEY:      {\"✅ Set\" if os.getenv(\"FINNHUB_API_KEY\") else \"❌ Not set (no news)\"}')
print()
print('=== Notification Status ===')
print(f'GMAIL_USER:        {\"✅ Set\" if os.getenv(\"GMAIL_USER\") else \"❌ Not set\"}')
print(f'IMESSAGE_RECIPIENT:{\"✅ Set\" if os.getenv(\"IMESSAGE_RECIPIENT\") else \"❌ Not set\"}')
"
```

---

## Step 8: Test Market Data Fetch

```bash
source venv/bin/activate
source .env

python -c "
from src.agents.market_analyst import MarketAnalyst
import os

ma = MarketAnalyst(
    'data/agent.db',
    api_key=os.getenv('ALPACA_API_KEY'),
    api_secret=os.getenv('ALPACA_SECRET_KEY')
)

print('Fetching market data for AAPL, MSFT, NVDA...')
data = ma.scan_symbols(['AAPL', 'MSFT', 'NVDA'])

for symbol, info in data.items():
    print(f'{symbol}: \${info[\"price\"]:.2f}, ATR: {info[\"atr\"]:.2f}, Volatile: {info[\"is_volatile\"]}')
"
```

---

## Step 9: Run the System

### Option A: Run Full Pipeline (Recommended First Test)

```bash
source venv/bin/activate
source .env

# Pre-market mode (safe - just scans and analyzes)
python src/main_orchestrator.py --mode premarket
```

### Option B: Force Market Mode (Generates Recommendations)

```bash
python src/main_orchestrator.py --mode market
```

### Option C: Post-market Summary

```bash
python src/main_orchestrator.py --mode postmarket
```

### Option D: Auto-detect Mode (Production Use)

```bash
python src/main_orchestrator.py
```

This automatically selects mode based on current time (Pacific):
- 6:00-6:30 AM: Pre-market
- 6:30 AM-1:00 PM: Market hours
- 1:00-2:00 PM: Post-market
- Other times: Closed (no action)

---

## Step 10: View Results

### Check Database for Recommendations

```bash
sqlite3 data/agent.db "
SELECT symbol, action, confidence, reasoning, datetime(timestamp) as time
FROM strategy_recommendations
ORDER BY timestamp DESC
LIMIT 5;
"
```

### Check Risk Decisions

```bash
sqlite3 data/agent.db "
SELECT symbol, action,
       CASE WHEN approved THEN '✅ Approved' ELSE '❌ Rejected' END as status,
       reason,
       datetime(timestamp) as time
FROM risk_decisions
ORDER BY timestamp DESC
LIMIT 5;
"
```

### Check News Analysis

```bash
sqlite3 data/agent.db "
SELECT symbol, sentiment, confidence, urgency, key_reason, datetime(timestamp) as time
FROM news_analysis
ORDER BY timestamp DESC
LIMIT 5;
"
```

### Check Screened Stocks

```bash
sqlite3 data/agent.db "
SELECT symbol, source, rank, datetime(screening_timestamp) as time
FROM screener_results
ORDER BY rank
LIMIT 10;
"
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

# Run system
python src/main_orchestrator.py --mode premarket   # Safe test
python src/main_orchestrator.py --mode market      # Get recommendations
python src/main_orchestrator.py --mode postmarket  # Daily summary
python src/main_orchestrator.py                    # Auto-detect mode

# Import new portfolio
python -c "
from src.agents.portfolio_accountant import PortfolioAccountant
pa = PortfolioAccountant('data/agent.db')
pa.import_fidelity_csv('inbox/your_file.csv')
"

# Check portfolio
sqlite3 data/agent.db "SELECT * FROM holdings WHERE snapshot_id = (SELECT MAX(id) FROM portfolio_snapshot);"

# Check recommendations
sqlite3 data/agent.db "SELECT * FROM strategy_recommendations ORDER BY timestamp DESC LIMIT 5;"

# Check screened stocks
sqlite3 data/agent.db "SELECT symbol, source, rank FROM screener_results ORDER BY rank LIMIT 10;"

# Run tests
python -m pytest tests/ -v
```
