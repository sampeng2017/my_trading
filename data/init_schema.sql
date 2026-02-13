-- Automated Stock Trading Intelligence System
-- Database Schema v1.0

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
    volume INTEGER,  -- Average daily volume for liquidity check
    is_volatile INTEGER DEFAULT 0,
    source TEXT CHECK(source IN ('Alpaca', 'Alpaca-Quote', 'YFinance', 'Manual'))
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
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_response TEXT,
    response_time DATETIME
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

-- Screener Results (cached screening outputs)
CREATE TABLE IF NOT EXISTS screener_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    source TEXT,
    screening_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rank INTEGER,
    score DECIMAL(5, 3),
    reason TEXT
);

-- Screener Run Log (audit trail)
CREATE TABLE IF NOT EXISTS screener_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    source TEXT,
    symbols_found INTEGER,
    symbols_after_filter INTEGER,
    error TEXT
);

-- Recommendation Evaluations (assessing past recommendation quality)
CREATE TABLE IF NOT EXISTS recommendation_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    original_action TEXT NOT NULL,
    original_confidence DECIMAL(3, 2),
    original_target_price DECIMAL(10, 4),
    original_stop_loss DECIMAL(10, 4),
    recommendation_date DATETIME NOT NULL,
    evaluation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    price_at_recommendation DECIMAL(10, 4),
    price_at_evaluation DECIMAL(10, 4),
    price_change_pct DECIMAL(8, 4),
    target_hit INTEGER DEFAULT 0,
    stop_loss_hit INTEGER DEFAULT 0,
    max_favorable_move_pct DECIMAL(8, 4),
    max_adverse_move_pct DECIMAL(8, 4),
    score TEXT CHECK(score IN ('excellent', 'good', 'neutral', 'poor', 'bad')),
    ai_assessment TEXT,
    FOREIGN KEY(recommendation_id) REFERENCES strategy_recommendations(id)
);

-- Orchestrator Runs (triggered via API or scheduled)
CREATE TABLE IF NOT EXISTS orchestrator_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL CHECK(mode IN ('premarket', 'market', 'postmarket', 'review', 'evaluate')),
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    triggered_by TEXT DEFAULT 'manual' CHECK(triggered_by IN ('manual', 'scheduled')),
    logs TEXT DEFAULT ''
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_analysis(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_holdings_snapshot ON holdings(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp ON strategy_recommendations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_timestamp ON portfolio_snapshot(import_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_screener_results_timestamp ON screener_results(screening_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_orchestrator_status ON orchestrator_runs(status);
CREATE INDEX IF NOT EXISTS idx_evaluations_date ON recommendation_evaluations(evaluation_date DESC);
CREATE INDEX IF NOT EXISTS idx_evaluations_symbol ON recommendation_evaluations(symbol, evaluation_date DESC);
