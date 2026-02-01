# Daily Trading Workflow

A practical guide for using the Stock Trading Intelligence System during market hours.

---

## Choose Your Mode

### Option A: Fully Automatic (Recommended)
Run once to set up, then system runs by itself:
```bash
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate
python scripts/setup_launchd.py
```

The system will automatically run at:
- 6:00 AM - Pre-market scan
- 6:35 AM - Market open recommendations
- 9:00 AM - Mid-morning check
- 11:00 AM - Mid-day check
- 1:05 PM - Post-market summary

You just receive iMessage alerts and decide whether to trade.

### Option B: Manual Control
Run commands yourself when you want:
```bash
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate

python scripts/run_system.py premarket      # Pre-market scan
python scripts/run_system.py market         # Get recommendations
python scripts/run_system.py postmarket     # Daily summary
```

---

## Quick Reference

```bash
# Setup (run once)
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate

# Main commands
python scripts/import_portfolio.py          # Import latest portfolio
python scripts/run_system.py premarket      # Pre-market scan
python scripts/run_system.py market         # Get recommendations
python scripts/run_system.py postmarket     # Daily summary
python scripts/check_database.py            # View results

# Automatic scheduling
python scripts/setup_launchd.py             # Enable auto-run
python scripts/setup_launchd.py --remove    # Disable auto-run
launchctl list | grep stockagent            # Check if running
tail -f logs/stdout.log                     # Watch live logs
```

---

## Timeline (Pacific Time)

| Time | Mode | What Happens |
|------|------|--------------|
| 6:00-6:30 AM | Pre-market | Stock screening, news analysis |
| 6:30 AM-1:00 PM | Market | Live recommendations |
| 1:00-2:00 PM | Post-market | Daily summary email |
| 9:00 PM-6:00 AM | Quiet Hours | No notifications |

---

## Step-by-Step: Tomorrow's Workflow

### 1. Before Market Open (6:00 AM)

#### 1.1 Export Fresh Portfolio from Fidelity

1. Log into [Fidelity.com](https://www.fidelity.com)
2. Go to **Accounts** → **Positions**
3. Click **Download** → **CSV**
4. Save to: `inbox/` folder (filename doesn't matter)

#### 1.2 Open Terminal and Setup Environment

```bash
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate
```

Note: `.env` is loaded automatically by python-dotenv.

#### 1.3 Import Your Portfolio

**Option A: Web Dashboard (Recommended)**
1. Go to http://localhost:8000/portfolio (or your Railway URL)
2. Scroll to "Import Portfolio CSV"
3. Drag and drop your Fidelity CSV or click "Choose File"
4. Page refreshes with new portfolio data

**Option B: Command Line**
```bash
python scripts/import_portfolio.py
```

Expected output:
```
📄 Using most recent CSV: Portfolio_Positions_Jan-30-2026.csv

📥 Importing: inbox/Portfolio_Positions_Jan-30-2026.csv
--------------------------------------------------

✅ Import successful! Snapshot #8

==================================================
                PORTFOLIO SUMMARY
==================================================
  Total Equity:  $   1,006,817.65
  Cash Balance:  $      10,634.58
  Invested:      $     996,183.07
  Positions:                   4

                     HOLDINGS
--------------------------------------------------
  Symbol       Shares   Cost Basis        Value
--------------------------------------------------
  MSFT       2,065.64 $    117.22 $895,453.11
  ORCL         596.00 $    265.23 $100,729.96
==================================================
```

#### 1.4 Run Pre-Market Scan (Optional but Recommended)

```bash
python scripts/run_system.py premarket
```

This will:
- Screen for tradeable stocks (Alpaca movers + AI ranking)
- Fetch latest news for your holdings
- Cache data for faster market-hours execution

---

### 2. During Market Hours (6:30 AM - 1:00 PM)

#### 2.1 Run the Trading System

```bash
python scripts/run_system.py market
```

Or let it auto-detect mode:
```bash
python scripts/run_system.py
```

#### 2.2 What the System Does

1. **Stock Screening**
   - Fetches top movers from Alpaca API
   - AI re-ranks candidates using Gemini (looks for breakout setups, momentum)
   - Adds top 10 screened stocks to monitoring list

2. **Portfolio Analysis**
   - Fetches live prices for MSFT, ORCL, and screened stocks
   - Calculates technical indicators (ATR, SMA-50)
   - Detects high volatility conditions

3. **News Analysis**
   - Fetches recent news from Finnhub
   - AI sentiment analysis (bullish/bearish/neutral)

4. **Strategy Generation**
   - AI generates BUY/SELL/HOLD recommendations
   - Uses Chain-of-Thought reasoning (Technical → Sentiment → Risk)
   - Assigns confidence scores (0-100)

5. **Risk Control**
   - Validates recommendations against hard limits:
     - Max 20% of portfolio in single stock
     - Max 40% in single sector
     - Minimum $200K daily volume
     - No short selling
   - Calculates position size and stop-loss

6. **Notifications**
   - Sends iMessage for approved trades
   - Logs everything to database

#### 2.3 Check Results

```bash
python scripts/check_database.py
```

Or for detailed view:
```bash
python scripts/check_database.py --full
```

#### 2.4 Understanding Recommendations

The system will send you recommendations like:

```
🚀 TRADE ALERT: AAPL

Action: BUY
Confidence: 78%
Shares: 45
Entry: $227.63
Stop-Loss: $218.10
Risk: $428.85 (1.5% of equity)

Reasoning: Strong momentum following earnings beat.
Technical breakout above SMA-50 with increasing volume.
```

**Important:**
- You decide whether to execute trades
- The system NEVER trades automatically
- Always verify recommendations before acting

---

### 3. After Market Close (1:00 PM)

#### 3.1 Run Post-Market Summary

```bash
python scripts/run_system.py postmarket
```

This sends a daily summary email with:
- Portfolio performance
- All recommendations made today
- Risk decisions (approved/rejected)

#### 3.2 Review the Day

**Option A: Use REST API (recommended)**
```bash
# Start API server (if not running)
uvicorn src.api.main:app --port 8000 &

# Get recommendations
curl -H "X-API-Key: dev-secret-key" "http://localhost:8000/agent/recommendations?limit=10"

# Get portfolio
curl -H "X-API-Key: dev-secret-key" http://localhost:8000/portfolio/summary
```

**Option B: Use Turso CLI (cloud database)**
```bash
turso db shell samtrading "SELECT symbol, action, confidence FROM strategy_recommendations ORDER BY timestamp DESC LIMIT 10;"
```

**Option C: Use sqlite3 (local database only)**
```bash
# Only works if DB_MODE=local
sqlite3 data/agent.db "SELECT symbol, action, confidence, reasoning FROM strategy_recommendations WHERE date(timestamp) = date('now') ORDER BY timestamp DESC;"
```

---

## What to Expect

### Your Current Portfolio

| Symbol | Shares | ~Value | % of Portfolio |
|--------|--------|--------|----------------|
| MSFT | 2,065 | $895,000 | 89% |
| ORCL | 596 | $100,000 | 10% |
| Cash | - | $10,600 | 1% |

### Risk Controller Behavior

Given your portfolio concentration:

1. **MSFT (89% of portfolio)**
   - Already exceeds 20% max position limit
   - System will likely NOT recommend buying more MSFT
   - May suggest trimming position

2. **ORCL (10% of portfolio)**
   - Within limits
   - May recommend adding if AI is bullish

3. **New Positions**
   - With $10,600 cash, max new position ≈ $10,000
   - System will size positions to risk 1.5% per trade (~$15,000 risk budget)

4. **Screened Stocks**
   - System will find 10 new opportunities daily
   - AI ranks them by momentum, volume, and setup quality
   - Only high-confidence (>60%) recommendations are sent

---

## Troubleshooting

### "No market data available"
- Markets may be closed (check if it's a trading day)
- Wait for market open (6:30 AM PT)

### "Gemini API error" or "429 Resource exhausted"
- **Rate limits are normal** with free tier (15 requests/minute)
- System will retry and continue with available data
- Check your API key: `echo $GEMINI_API_KEY`
- Verify at https://aistudio.google.com/apikey
- Consider spacing out runs if seeing many 429 errors

### "No recommendations generated"
- Normal if market conditions are poor
- Check logs: `python scripts/check_database.py --full`

### iMessage not working
- Grant Terminal access: System Settings → Privacy → Automation → Terminal → Messages

### Import shows $0
- Make sure you're using fresh Fidelity CSV export
- Check CSV has data rows (not just headers)

---

## Automatic Scheduling Setup

### Enable Automatic Mode (One-Time Setup)

```bash
cd /Users/shengpeng/study/repo/my_trading
source venv/bin/activate
python scripts/setup_launchd.py
```

This will:
1. Read your API keys from `.env`
2. Create a launchd schedule
3. Run the system automatically at market times

### Schedule (Pacific Time)

| Time | Mode | What Happens |
|------|------|--------------|
| 6:00 AM | Pre-market | News scan, stock screening |
| 6:35 AM | Market | Live recommendations |
| 9:00 AM | Market | Mid-morning check |
| 11:00 AM | Market | Mid-day check |
| 1:05 PM | Post-market | Daily summary email |

### Managing the Schedule

```bash
# Check if running
launchctl list | grep stockagent

# View live logs
tail -f logs/stdout.log

# Disable automatic mode
python scripts/setup_launchd.py --remove
```

---

## Keeping MacBook Awake (Required for Automatic Mode)

For scheduled tasks to run, your MacBook must be awake. Here's how to set it up:

### Step 1: Schedule Automatic Wake-Up (One-Time)

```bash
# Wake Mac at 5:55 AM every weekday (before market)
sudo pmset repeat wakeorpoweron MTWRF 05:55:00

# Verify the schedule
pmset -g sched
```

### Step 2: Keep Awake During Market Hours

**Option A: Simple - Leave MacBook open and plugged in**
- Screen will dim but Mac stays awake
- Easiest and most reliable

**Option B: Use caffeinate script**
```bash
# Run each morning (keeps Mac awake for 8 hours)
./scripts/keep_awake.sh &
```

**Option C: Add to Login Items**
1. System Settings → General → Login Items
2. Add `scripts/keep_awake.sh`
3. Mac stays awake automatically after login

### Requirements Checklist

| Requirement | Why |
|-------------|-----|
| ✅ **Plugged in** | Mac won't wake on battery |
| ✅ **Lid open OR external monitor** | Closed lid = sleep (unless external display) |
| ✅ **Don't manually sleep** | Apple menu → Sleep overrides schedule |

### Will Scripts Run?

| Scenario | Works? |
|----------|--------|
| Lid open, plugged in, idle | ✅ Yes |
| Lid closed + external monitor, plugged in | ✅ Yes |
| Lid closed, no monitor | ❌ No |
| On battery | ⚠️ Unreliable |

### Remove Wake Schedule

```bash
sudo pmset repeat cancel
```

---

## Auto-Import CSVs (Optional)

Run the watchdog to auto-import when you drop CSVs:
```bash
python src/utils/watchdog_csv.py &
```

Now just save Fidelity CSVs to `inbox/` and they import automatically.

---

## Files You'll Use Most

| File | Purpose |
|------|---------|
| `scripts/import_portfolio.py` | Import Fidelity CSV |
| `scripts/run_system.py` | Run trading system |
| `scripts/check_database.py` | View results |
| `scripts/test_phase1_db.py` | Test database connection |
| `inbox/` | Drop CSV files here |
| `logs/stdout.log` | System logs |

### Database Access

| Mode | How to Query |
|------|--------------|
| Cloud (Turso) | `turso db shell samtrading` |
| Local (SQLite) | `sqlite3 data/agent.db` |
| REST API | `curl http://localhost:8000/...` |

Start API: `uvicorn src.api.main:app --port 8000`
API Docs: http://localhost:8000/docs

### Database Backup/Restore

```bash
# Backup cloud data to local (recommended weekly)
python scripts/sync_db.py --backup

# Restore local backup to cloud (if needed)
python scripts/sync_db.py --restore
```

---

## Safety Reminders

1. **Human-in-the-Loop**: System recommends, YOU decide
2. **No Automatic Trading**: System never executes trades
3. **Risk Limits Enforced**:
   - Max 20% per stock
   - Max 40% per sector
   - 1.5% risk per trade
4. **Stop-Loss Calculated**: Every recommendation includes exit price
5. **All Decisions Logged**: Full audit trail in database

---

## Tomorrow's Checklist

- [ ] Export Fidelity CSV before 6:30 AM
- [ ] Run `python scripts/import_portfolio.py`
- [ ] Run `python scripts/run_system.py` at market open
- [ ] Check iMessage/email for alerts
- [ ] Review recommendations before acting
- [ ] Run `python scripts/check_database.py` to see all results

Good luck trading!
