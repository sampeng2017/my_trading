# Cloud Migration Guide

Complete guide to migrate the trading system to the cloud for cross-device access.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Phase 1: Cloud Database (Turso)](#phase-1-cloud-database-turso)
4. [Phase 2: REST API](#phase-2-rest-api)
5. [Phase 3: Web Dashboard](#phase-3-web-dashboard)
6. [Phase 4: Cloud Deployment (Railway)](#phase-4-cloud-deployment-railway)
7. [Phase 5: Notification Updates](#phase-5-notification-updates)
8. [Verification Checklist](#verification-checklist)
9. [Rollback Procedures](#rollback-procedures)

---

## Overview

### Current Architecture
- Local SQLite database (`data/agent.db`)
- Scheduled runs via Mac cron/launchd
- iMessage notifications (macOS-only)

### Target Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                         CLOUD                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   Turso     │◄───│  FastAPI    │◄───│  Web Dashboard  │  │
│  │  (SQLite)   │    │   Backend   │    │  (HTMX/Jinja)   │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│         ▲                  ▲                    ▲            │
│         │                  │                    │            │
│  ┌──────┴──────┐    ┌──────┴──────┐      ┌─────┴─────┐     │
│  │  Trading    │    │  Scheduler  │      │  Phone /  │     │
│  │  Agents     │    │  (Railway)  │      │  Browser  │     │
│  └─────────────┘    └─────────────┘      └───────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### What Each Phase Enables

| Phase | Capability |
|-------|------------|
| 1. Cloud Database | View data from any device (via CLI) |
| 2. REST API | Programmatic access, foundation for UI |
| 3. Web Dashboard | Full phone/browser access |
| 4. Cloud Deploy | Mac becomes optional, runs automatically |
| 5. Notifications | Email alerts (cross-platform) |

---

## Prerequisites

### Required Accounts (Free Tiers)

| Service | Purpose | Sign Up URL |
|---------|---------|-------------|
| **Turso** | Cloud SQLite database | https://turso.tech |
| **Railway** | App hosting & scheduling | https://railway.app |
| **GitHub** | Code repository (for deployment) | https://github.com |

### Required Tools

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Turso CLI
brew install tursodatabase/tap/turso

# Railway CLI
brew install railway

# Python 3.10+ (likely already installed)
python3 --version
```

---

## Phase 1: Cloud Database (Turso)

### Step 1.1: Create Turso Account

1. Go to https://turso.tech
2. Click "Start for free"
3. Sign up with GitHub (recommended) or email
4. Verify your email if prompted

### Step 1.2: Install and Authenticate Turso CLI

```bash
# Install CLI
brew install tursodatabase/tap/turso

# Login (opens browser)
turso auth login

# Verify login
turso auth whoami
```

### Step 1.3: Create Database

```bash
# Create the database
turso db create trading-system

# View database info (save the URL)
turso db show trading-system

# Example output:
# Name:           trading-system
# URL:            libsql://trading-system-yourusername.turso.io
# ID:             xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# Group:          default
# Version:        0.24.0
# Locations:      sjc
# Size:           0 B
```

### Step 1.4: Create Auth Token

```bash
# Create a token (save this securely!)
turso db tokens create trading-system

# Output will be a long string like:
# eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...
```

**Important**: Save both the URL and token. You'll need them for environment variables.

### Step 1.5: Initialize Schema

```bash
# Navigate to project directory
cd /Users/shengpeng/study/repo/my_trading

# Load schema into Turso
turso db shell trading-system < data/init_schema.sql

# Verify tables were created
turso db shell trading-system "SELECT name FROM sqlite_master WHERE type='table'"
```

Expected output:
```
portfolio_snapshot
holdings
market_data
news_analysis
strategy_recommendations
risk_decisions
trade_log
notification_log
stock_metadata
screener_results
screener_runs
```

### Step 1.6: Install Python Dependencies

```bash
# Add to requirements.txt
echo "libsql-experimental>=0.0.34" >> requirements.txt

# Install
pip install libsql-experimental
```

### Step 1.7: Update Environment Variables

Add to your `.env` file (python-dotenv format, no `export`):

```bash
# Database Configuration
DB_MODE=turso
TURSO_DATABASE_URL=libsql://trading-system-yourusername.turso.io
TURSO_AUTH_TOKEN=your-token-here
```

**Note**: This project uses `python-dotenv` which loads `.env` automatically. Do NOT use `export` - just `KEY=VALUE`.

### Step 1.8: Code Changes for Phase 1

**Create `src/data/db_connection.py`:**

```python
"""
Database connection adapter supporting both local SQLite and Turso cloud.

Environment variables are read at call time (not import time) so changes
take effect without restarting the process.
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any


def _get_db_config():
    """Read database config from environment at call time."""
    return {
        'mode': os.environ.get('DB_MODE', 'local'),
        'turso_url': os.environ.get('TURSO_DATABASE_URL', ''),
        'turso_token': os.environ.get('TURSO_AUTH_TOKEN', ''),
    }


@contextmanager
def get_connection(db_path: str = None) -> Generator[Any, None, None]:
    """
    Get database connection based on DB_MODE environment variable.

    Args:
        db_path: Path to local SQLite database (used when DB_MODE='local')

    Yields:
        Database connection object (sqlite3.Connection or libsql Connection)
    """
    config = _get_db_config()

    if config['mode'] == 'turso' and config['turso_url']:
        import libsql_experimental as libsql
        conn = libsql.connect(config['turso_url'], auth_token=config['turso_token'])
    else:
        if not db_path:
            raise ValueError("db_path required for local SQLite mode")
        conn = sqlite3.connect(db_path)

    try:
        yield conn
    finally:
        conn.close()


def get_db_mode() -> str:
    """Return current database mode."""
    return _get_db_config()['mode']
```

**Update each agent file** (example for `portfolio_accountant.py`):

Before:
```python
conn = sqlite3.connect(self.db_path)
cursor = conn.cursor()
cursor.execute("...")
conn.commit()
conn.close()
```

After:
```python
from data.db_connection import get_connection

with get_connection(self.db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("...")
    conn.commit()
```

### Step 1.9: Migrate Existing Data (Optional)

If you have existing data in local SQLite:

```bash
# Export from local SQLite
sqlite3 data/agent.db ".dump" > data/backup.sql

# Import to Turso (may need to edit SQL for compatibility)
turso db shell trading-system < data/backup.sql
```

### Step 1.10: Verify Phase 1

**Note**: `python-dotenv` loads `.env` when you import `src.utils.config`. For standalone scripts, call `load_dotenv()` explicitly first.

```bash
# Verify Turso mode
python -c "
# Load .env first (before importing modules that read env vars)
from dotenv import load_dotenv
load_dotenv()

from src.data.db_connection import get_connection, get_db_mode
print(f'Database mode: {get_db_mode()}')

# For Turso mode, db_path is not needed
# For local mode, you would pass: get_connection('data/agent.db')
if get_db_mode() == 'turso':
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM portfolio_snapshot')
        print(f'Portfolio snapshots: {cursor.fetchone()[0]}')
else:
    print('Still in local mode. Set DB_MODE=turso in .env')
"
```

**Troubleshooting**: If you see "local" mode but expected "turso":
1. Check `.env` has `DB_MODE=turso` (no `export`, no quotes around value)
2. Ensure `.env` is in project root
3. Call `load_dotenv()` BEFORE importing modules that read env vars
4. Restart your Python process after editing `.env`

---

## Phase 2: REST API

### Step 2.1: Install API Dependencies

```bash
# Add to requirements.txt
cat >> requirements.txt << 'EOF'
fastapi>=0.109.0
uvicorn>=0.27.0
python-multipart>=0.0.9
httpx>=0.27.0
EOF

# Install
pip install fastapi uvicorn python-multipart httpx
```

### Step 2.2: Create API Structure

```bash
mkdir -p src/api/routers
touch src/api/__init__.py
touch src/api/routers/__init__.py
```

### Step 2.3: Authentication (API Key Only)

For Phase 2, we implement a **Secure by Default** approach using a strict API Key strategy. OAuth is deferred to Phase 3 (Web Dashboard).

- **Method**: `X-API-Key` Header
- **Scope**: Global (All endpoints protected)
- **Safety**: No default keys allowed in production

#### 2.3.1: Configure Environment

Add to `.env`:
```bash
# API Security
API_KEY=your-secure-random-key-here
```

Generate a secure key:
```bash
python -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))"
```

#### 2.3.2: Create Auth Dependency

**`src/api/dependencies.py`**:

```python
import os
from fastapi import Header, HTTPException, status
from typing import Optional

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
   api_key = os.getenv("API_KEY")
   
   if not api_key:
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail="Server Authorization Misconfigured"
       )
   
   if x_api_key is None or x_api_key != api_key:
       raise HTTPException(
           status_code=status.HTTP_401_UNAUTHORIZED,
           detail="Invalid or Missing API Key"
       )
   return x_api_key
```

### Step 2.4: Create API Files

**`src/api/main.py`** - Main FastAPI application

```python
"""
Trading System API
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import market, portfolio, agent
from src.api.dependencies import verify_api_key
from fastapi import Depends

# Load env vars
load_dotenv()

app = FastAPI(title="Trading System API")

# CORS (Secure configuration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers - All protected by verify_api_key for Phase 2
app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(verify_api_key)])
app.include_router(market.router, prefix="/market", tags=["market"], dependencies=[Depends(verify_api_key)])
app.include_router(agent.router, prefix="/agent", tags=["agent"], dependencies=[Depends(verify_api_key)])

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

**`src/api/routers/portfolio.py`** (Example with DI)

```python
from fastapi import APIRouter, Depends
from src.agents.portfolio_accountant import PortfolioAccountant
from src.api.dependencies import get_portfolio_accountant

# Note: Auth dependencies are applied at the router level in main.py
router = APIRouter()

@router.get("/summary")
async def get_summary(pa: PortfolioAccountant = Depends(get_portfolio_accountant)):
    return pa.get_portfolio_summary()
```

---

### Step 2.5: Run API Locally

```bash
# Start development server
uvicorn src.api.main:app --reload --port 8000

# Test public endpoints
curl http://localhost:8000/health

# Test protected endpoints via API key
curl -H "X-API-Key: your-secure-key" http://localhost:8000/portfolio/summary
```

> **Transition Context**: Phase 3 will introduce GitHub OAuth for the web dashboard. Until then, use the API key for all programmatic access.

---

## Phase 3: Web Dashboard & OAuth

This phase introduces a browser-based dashboard authenticated via GitHub OAuth.

> **Auth Coexistence**: API routes (`/portfolio`, `/market`, `/agent`) remain protected by `X-API-Key` for programmatic access. Dashboard routes use OAuth session for browser-based access. The dashboard fetches data server-side, so no API key is needed in the browser.

### Step 3.1: Install Auth & Template Dependencies

```bash
# Add to requirements.txt
cat >> requirements.txt << 'EOF'
authlib>=1.3.0
itsdangerous>=2.1.0
jinja2>=3.1.0
EOF

# Install (note: httpx already installed from Phase 2)
pip install authlib itsdangerous jinja2
```

### Step 3.2: Configure GitHub OAuth

1. Go to https://github.com/settings/developers
2. "New OAuth App":
   - **Name**: `Trading System`
   - **Homepage**: `http://localhost:8000`
   - **Callback URL**: `http://localhost:8000/auth/callback`
3. Copy **Client ID** and generate **Client Secret**.

Add to `.env`:
```bash
# OAuth Config
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
GITHUB_ALLOWED_USERS=your-github-username
SESSION_SECRET=your-random-secret
```

Generate session secret:
```bash
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))"
```

### Step 3.3: Implement Auth Module

**`src/api/auth.py`**:

```python
import os
from typing import Optional
from fastapi import Request
from authlib.integrations.starlette_client import OAuth

def get_config():
    return {
        'github_client_id': os.environ.get('GITHUB_CLIENT_ID'),
        'github_client_secret': os.environ.get('GITHUB_CLIENT_SECRET'),
        'allowed_users': [u.strip() for u in os.environ.get('GITHUB_ALLOWED_USERS', '').split(',')],
        'session_secret': os.environ.get('SESSION_SECRET'),
    }

oauth = OAuth()

def init_oauth():
    oauth.register(
        name='github',
        client_id=os.environ.get('GITHUB_CLIENT_ID'),
        client_secret=os.environ.get('GITHUB_CLIENT_SECRET'),
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'read:user'},
    )

async def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get('user')
```

### Step 3.4: Implement Auth Routes

**`src/api/routers/auth.py`**:

```python
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from src.api.auth import oauth, get_config

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for('auth_callback')
    return await oauth.github.authorize_redirect(request, redirect_uri)

@router.get("/callback")
async def auth_callback(request: Request):
    token = await oauth.github.authorize_access_token(request)
    resp = await oauth.github.get('user', token=token)
    user_data = resp.json()
    
    config = get_config()
    if user_data['login'] not in config['allowed_users']:
        return RedirectResponse(url="/?error=unauthorized")
    
    request.session['user'] = {'username': user_data['login']}
    return RedirectResponse(url="/")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
```

### Step 3.5: Update Main Application

Update **`src/api/main.py`** to include session middleware and auth routes:

```python
from starlette.middleware.sessions import SessionMiddleware
from src.api.auth import init_oauth
from src.api.routers import auth
from src.dashboard import routes as dashboard  # Dashboard router

# ... existing app setup ...

# Add Session Middleware (BEFORE routers)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET"))

# Initialize OAuth
init_oauth()

# Include Auth Router (NOT protected by API Key)
app.include_router(auth.router)

# Include Dashboard Router (NOT protected by API Key - uses OAuth session)
# Note: Dashboard fetches data server-side via direct agent calls, NOT via API endpoints
app.include_router(dashboard.router, tags=["dashboard"])
```

> **Key Point**: The dashboard router is included *without* the `dependencies=[Depends(verify_api_key)]` parameter. It uses OAuth session for auth and accesses data via direct Python imports, bypassing the API layer entirely.

### Step 3.6: Create Dashboard Structure

```bash
mkdir -p src/dashboard/templates
mkdir -p src/dashboard/static/css
touch src/dashboard/__init__.py
touch src/dashboard/routes.py  # Dashboard routes (defined in Step 3.8)
```

### Step 3.7: Create Templates

**`src/dashboard/templates/base.html`** - Base layout with login/logout button

```html
<!DOCTYPE html>
<html>
<head>
    <title>Trading System</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
</head>
<body>
    <nav>
        {% if user %}
            <span>{{ user.username }}</span>
            <a href="/auth/logout">Logout</a>
        {% else %}
            <a href="/auth/login">Login with GitHub</a>
        {% endif %}
    </nav>
    {% block content %}{% endblock %}
</body>
</html>
```

**`src/dashboard/templates/index.html`** - Dashboard home
**`src/dashboard/templates/portfolio.html`** - Holdings view
**`src/dashboard/templates/recommendations.html`** - Trade recommendations

### Step 3.8: Add Dashboard Routes to FastAPI

```python
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from src.api.auth import get_current_user
from src.api.dependencies import get_portfolio_accountant  # Server-side data access

router = APIRouter()
templates = Jinja2Templates(directory="src/dashboard/templates")

@router.get("/")
async def dashboard_home(request: Request):
    user = await get_current_user(request)
    # Server-side data fetch (no API key needed in browser)
    pa = get_portfolio_accountant()
    portfolio = pa.get_portfolio_summary()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "portfolio": portfolio,
    })
```

### Step 3.9: Test Dashboard

```bash
# Start server
uvicorn src.api.main:app --reload --port 8000

# Open in browser
open http://localhost:8000

# Test flow:
# 1. View portfolio (server-side rendering, no API key needed)
# 2. Click "Login with GitHub"
# 3. Authorize the app
# 4. Now you can trigger runs and approve trades
```

---

## Phase 4: Cloud Deployment (Railway)

### Step 4.1: Create Railway Account

1. Go to https://railway.app
2. Click "Login" → "Login with GitHub"
3. Authorize Railway to access your GitHub
4. Complete account setup

### Step 4.2: Install Railway CLI

```bash
# Install
brew install railway

# Login (opens browser)
railway login

# Verify
railway whoami
```

### Step 4.3: Prepare Project for Deployment

**Create `Procfile`:**
```
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

**Create `runtime.txt`:**
```
python-3.11.0
```

**Create `railway.toml`:**
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn src.api.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/api/status"
healthcheckTimeout = 100
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Step 4.4: Push Code to GitHub

```bash
# If not already a git repo with remote
git remote add origin https://github.com/yourusername/my_trading.git
git push -u origin main
```

### Step 4.5: Create Railway Project

```bash
# Create new project
railway init

# Or link to existing project
railway link
```

### Step 4.6: Configure Environment Variables in Railway

```bash
# Generate secrets first
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))"

# Database
railway variables set DB_MODE=turso
railway variables set TURSO_DATABASE_URL="libsql://trading-system-yourusername.turso.io"
railway variables set TURSO_AUTH_TOKEN="your-token"

# Authentication (CRITICAL for security)
railway variables set GITHUB_CLIENT_ID="your-github-client-id"
railway variables set GITHUB_CLIENT_SECRET="your-github-client-secret"
railway variables set GITHUB_ALLOWED_USERS="your-github-username"  # No spaces if multiple: user1,user2
railway variables set SESSION_SECRET="your-generated-session-secret"
railway variables set API_KEY="your-generated-api-key"

# Trading APIs
railway variables set GEMINI_API_KEY="your-gemini-key"
railway variables set ALPACA_API_KEY="your-alpaca-key"
railway variables set ALPACA_SECRET_KEY="your-alpaca-secret"
railway variables set FINNHUB_API_KEY="your-finnhub-key"
railway variables set ALPHA_VANTAGE_API_KEY="your-alphavantage-key"
```

**Important**: Update your GitHub OAuth App callback URL to your Railway domain:
1. Go to https://github.com/settings/developers
2. Edit your OAuth App
3. Change callback URL to: `https://your-app.up.railway.app/auth/callback`

Or use Railway dashboard:
1. Go to https://railway.app/dashboard
2. Select your project
3. Click "Variables"
4. Add each variable

### Step 4.7: Deploy

```bash
# Deploy from CLI
railway up

# Or push to GitHub (auto-deploys if connected)
git push origin main
```

### Step 4.8: Set Up Scheduled Runs (Cron)

Railway supports cron jobs. Create a separate service:

**Important**: Railway cron uses **UTC timezone**. Convert your local times:
- Pacific 6:30 AM = **14:30 UTC** (or 13:30 during DST)
- Pacific 1:00 PM = **21:00 UTC** (or 20:00 during DST)

1. In Railway dashboard, click "New Service"
2. Select "Cron Job"
3. Set schedule: `30 14,21 * * 1-5` (UTC times for Pacific 6:30 AM and 1:00 PM, weekdays)
4. Set command: `python src/main_orchestrator.py`

Or use Railway's `railway.toml`:
```toml
[[services]]
name = "web"
startCommand = "uvicorn src.api.main:app --host 0.0.0.0 --port $PORT"

[[crons]]
name = "trading-premarket"
schedule = "30 14 * * 1-5"  # 6:30 AM Pacific (UTC)
command = "python src/main_orchestrator.py --mode premarket"

[[crons]]
name = "trading-postmarket"
schedule = "0 21 * * 1-5"   # 1:00 PM Pacific (UTC)
command = "python src/main_orchestrator.py --mode postmarket"
```

**Timezone reference** (standard time, adjust +1 hour during DST):
| Pacific Time | UTC |
|--------------|-----|
| 6:00 AM | 14:00 |
| 6:30 AM | 14:30 |
| 1:00 PM | 21:00 |
| 2:00 PM | 22:00 |

### Step 4.9: Verify Deployment

```bash
# Get deployment URL
railway open

# Or check status
railway status
```

Your app will be available at: `https://your-project.up.railway.app`

---

## Phase 5: Notification Updates

### Step 5.1: Update Notification Specialist

Modify `src/agents/notification_specialist.py` to:
- Remove iMessage/AppleScript code (macOS-only)
- Keep email functionality
- Add environment check for cloud vs local

### Step 5.2: Update Configuration

In `config/config.yaml`, add:
```yaml
notifications:
  channels:
    email: true
    imessage: false  # Disabled for cloud deployment
```

### Step 5.3: Verify Email Works in Cloud

```bash
# Test email notification
python -c "
from src.agents.notification_specialist import NotificationSpecialist
ns = NotificationSpecialist()
ns.send_email('Test from cloud', 'This is a test email.')
"
```

---

## Verification Checklist

### Phase 1 Complete
- [ ] Turso account created
- [ ] Database created and schema loaded
- [ ] Auth token saved in `.env`
- [ ] `libsql-experimental` installed
- [ ] `db_connection.py` created
- [ ] Agent files updated to use `get_connection()`
- [ ] Can query Turso from Python

### Phase 2 Complete
 - [ ] FastAPI installed
 - [ ] API structure created (`src/api/routers`)
 - [ ] Security: `API_KEY` set in environment
 - [ ] Dependencies installed (`fastapi`, `uvicorn`, `httpx`)
 - [ ] `/portfolio/summary` returns data (via API Key)
 - [ ] `/market/price/{symbol}` returns data (via API Key)
 - [ ] `/health` returns system info (Public)
 - [ ] `/portfolio/*`, `/market/*`, `/agent/*` return 401 if key missing
 - [ ] Unit tests passing with `API_KEY` set
 
 ### Phase 3 Complete
 - [ ] Auth dependencies installed (`authlib`, `itsdangerous`, `jinja2`) + `httpx` from Phase 2
 - [ ] GitHub OAuth App created & Client ID/Secret saved
 - [ ] `SESSION_SECRET` set
 - [ ] Configuration updated with `GITHUB_ALLOWED_USERS`
 - [ ] Authentication logic implemented (`src/api/auth.py`)
 - [ ] Dashboard templates created
 - [ ] `/auth/login` redirects to GitHub
 - [ ] Dashboard accessible at `http://localhost:8000`
 - [ ] Can view portfolio on browser (Login required for actions)

### Phase 4 Complete
- [ ] Railway account created
- [ ] Project deployed
- [ ] Environment variables set in Railway (including `API_KEY`)
- [ ] App accessible at Railway URL
- [ ] **Security check**: `/api/run` without API key returns 401
- [ ] **Security check**: `/api/run` with API key works
- [ ] Cron job scheduled for trading runs (in UTC!)
- [ ] Verify scheduled run executes

### Phase 5 Complete
- [ ] iMessage code removed/disabled
- [ ] Email notifications working from cloud
- [ ] Receive email after scheduled run

---

## Rollback Procedures

### Revert to Local SQLite

```bash
# Change environment variable
export DB_MODE="local"

# Or in .env file
DB_MODE=local
```

The system will immediately use local SQLite instead of Turso.

### Keep Local Backup

Always maintain a local SQLite backup:

```bash
# Export from Turso periodically
turso db shell trading-system ".dump" > data/turso_backup_$(date +%Y%m%d).sql
```

### Railway Rollback

```bash
# View deployment history
railway deployments

# Rollback to previous deployment
railway rollback
```

---

## Cost Summary

### Free Tier Limits

| Service | Free Tier | Expected Usage |
|---------|-----------|----------------|
| **Turso** | 9GB storage, 500M reads/mo | ~60K reads/mo |
| **Railway** | $5 credit/mo, 500 hrs | ~$3-4/mo usage |

### When You Might Need Paid

- Turso: Unlikely unless storing years of history
- Railway: If running 24/7, may exceed free hours; ~$5-10/mo

---

## Troubleshooting

### App Fails to Start with "Missing required environment variables"

The app validates all required auth variables at startup and fails fast if any are missing.

```
RuntimeError: Missing required environment variables:
  - SESSION_SECRET is required
  - GITHUB_CLIENT_ID is required
```

**Fix**: Set all required variables in `.env` or Railway environment:
- `SESSION_SECRET` - Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `GITHUB_CLIENT_ID` - From GitHub OAuth App
- `GITHUB_CLIENT_SECRET` - From GitHub OAuth App
- `GITHUB_ALLOWED_USERS` - Your GitHub username(s)
- `API_KEY` - Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### GitHub Login Fails / "Unauthorized" After Login

1. **GITHUB_ALLOWED_USERS is empty or wrong**: Check the username matches exactly (case-sensitive)
2. **Multiple users format issue**: Use `user1,user2` (no spaces, or spaces are OK but be consistent)
3. **OAuth callback URL mismatch**: Ensure GitHub OAuth App callback URL matches your domain

### Turso Connection Fails

```bash
# Verify token is valid
turso db tokens list trading-system

# Create new token if expired
turso db tokens create trading-system
```

### Railway Deploy Fails

```bash
# View logs
railway logs

# Check build output
railway logs --build
```

### Database Locked Errors

Turso handles concurrency better than local SQLite, but if issues occur:

```python
# Add retry logic in db_connection.py
import time

def get_connection_with_retry(db_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            return get_connection(db_path)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))
```
