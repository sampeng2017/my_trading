# Trading System Architecture Diagrams

## 1. System Overview

```mermaid
graph TB
    subgraph External["External Services"]
        ALPACA[Alpaca API]
        FINNHUB[Finnhub News]
        GEMINI[Google Gemini AI]
        YFINANCE[yfinance]
        TURSO[Turso Cloud]
    end

    subgraph Core["Core System"]
        ORCH[Main Orchestrator]
        API[REST API<br/>FastAPI]
        DB[(Database<br/>SQLite/Turso)]
    end

    subgraph Agents["Agent Pipeline"]
        PA[Portfolio Accountant]
        SS[Stock Screener]
        MA[Market Analyst]
        NA[News Analyst]
        SP[Strategy Planner]
        RC[Risk Controller]
        NS[Notification Specialist]
    end

    subgraph Output["User Notifications"]
        IMSG[iMessage]
        EMAIL[Email]
    end

    CSV[Fidelity CSV] --> PA
    PA --> DB
    SS --> ALPACA
    MA --> ALPACA
    MA --> YFINANCE
    NA --> FINNHUB
    NA --> GEMINI
    SP --> GEMINI

    ORCH --> PA
    ORCH --> SS
    ORCH --> MA
    ORCH --> NA
    ORCH --> SP
    ORCH --> RC
    ORCH --> NS

    DB --> MA
    DB --> NA
    DB --> SP
    DB --> RC

    NS --> IMSG
    NS --> EMAIL
```

## 2. Agent Pipeline Flow

```mermaid
flowchart LR
    subgraph Collection["Data Collection"]
        direction TB
        A1[Portfolio Accountant<br/>Parse CSV, snapshot holdings]
        A2[Stock Screener<br/>Find tradeable stocks]
        A3[Market Analyst<br/>Fetch prices, ATR, SMA]
        A4[News Analyst<br/>Sentiment analysis]
    end

    subgraph Analysis["Analysis"]
        A5[Strategy Planner<br/>AI recommendations]
    end

    subgraph Safety["Safety & Output"]
        A6[Risk Controller<br/>Hard constraints]
        A7[Notification Specialist<br/>iMessage + Email]
    end

    A1 --> A2
    A2 --> A3
    A3 --> A4
    A4 --> A5
    A5 --> A6
    A6 --> A7

    style A1 fill:#e1f5fe
    style A2 fill:#e1f5fe
    style A3 fill:#e1f5fe
    style A4 fill:#fff3e0
    style A5 fill:#fff3e0
    style A6 fill:#ffebee
    style A7 fill:#e8f5e9
```

## 3. Time-Based Execution Modes

```mermaid
flowchart TB
    subgraph Schedule["Daily Schedule (Pacific Time)"]
        direction LR
        T1["6:00 AM"] --> T2["6:30 AM"] --> T3["1:00 PM"] --> T4["2:00 PM"]
    end

    subgraph PreMarket["PreMarket (6:00-6:30 AM)"]
        direction TB
        P1[Import CSV] --> P2[Populate Metadata]
        P2 --> P3[Screen Stocks]
    end

    subgraph Market["Market Hours (6:30 AM-1:00 PM)"]
        direction TB
        M1[Get Symbols] --> M2[Update Market Data]
        M2 --> M3[Analyze News]
        M3 --> M4[Generate Recommendations]
        M4 --> M5[Validate Risk]
        M5 --> M6[Send Alerts]
    end

    subgraph Post["PostMarket (1:00-2:00 PM)"]
        direction TB
        PM1[Send Daily Summary] --> PM2[Log Portfolio]
    end

    T1 -.-> PreMarket
    T2 -.-> Market
    T3 -.-> Post
    T4 -.-> Closed[Closed]

    style PreMarket fill:#e3f2fd
    style Market fill:#e8f5e9
    style Post fill:#fff3e0
    style Closed fill:#fafafa
```

## 4. Market Data Fetching (Fallback Chain)

```mermaid
flowchart TD
    START[Fetch Market Data] --> ALPACA{Alpaca Bars<br/>Available?}

    ALPACA -->|Yes| PARSE_ALPACA[Parse Alpaca DataFrame]
    ALPACA -->|No/Error| YFINANCE{yfinance<br/>Available?}

    YFINANCE -->|Yes| PARSE_YF[Parse yfinance Data]
    YFINANCE -->|No/Error| QUOTE{Alpaca Quote<br/>Available?}

    QUOTE -->|Yes| PARSE_QUOTE[Use Quote Price Only<br/>ATR/SMA = None]
    QUOTE -->|No/Error| FAIL[Return None<br/>Symbol Skipped]

    PARSE_ALPACA --> CALC[Calculate ATR + SMA-50]
    PARSE_YF --> CALC

    CALC --> SAVE[(Save to market_data)]
    PARSE_QUOTE --> SAVE

    style ALPACA fill:#c8e6c9
    style YFINANCE fill:#fff9c4
    style QUOTE fill:#ffccbc
    style FAIL fill:#ffcdd2
```

## 5. Risk Controller Validation

```mermaid
flowchart TD
    REC[Recommendation<br/>BUY/SELL] --> HOLD{Action = HOLD?}

    HOLD -->|Yes| APPROVE1[Approved<br/>No action needed]
    HOLD -->|No| CASH{Sufficient<br/>Cash?}

    CASH -->|No| REJECT1[Rejected<br/>Insufficient cash]
    CASH -->|Yes| POS{Position Size<br/>≤ 20%?}

    POS -->|No| REJECT2[Rejected<br/>Position too large]
    POS -->|Yes| SECTOR{Sector Exposure<br/>≤ 40%?}

    SECTOR -->|No| REJECT3[Rejected<br/>Sector concentration]
    SECTOR -->|Yes| SHORT{Not Shorting?}

    SHORT -->|No| REJECT4[Rejected<br/>No shorting allowed]
    SHORT -->|Yes| VOL{Volatility<br/>≤ 10%?}

    VOL -->|No| REJECT5[Rejected<br/>Too volatile]
    VOL -->|Yes| LIQ{Avg Volume<br/>≥ 200K?}

    LIQ -->|No| REJECT6[Rejected<br/>Low liquidity]
    LIQ -->|Yes| APPROVE2[Approved<br/>Calculate position size]

    style APPROVE1 fill:#c8e6c9
    style APPROVE2 fill:#c8e6c9
    style REJECT1 fill:#ffcdd2
    style REJECT2 fill:#ffcdd2
    style REJECT3 fill:#ffcdd2
    style REJECT4 fill:#ffcdd2
    style REJECT5 fill:#ffcdd2
    style REJECT6 fill:#ffcdd2
```

## 6. Stock Screener Flow

```mermaid
flowchart TD
    START[Screen Stocks] --> CACHE{Cache Valid?<br/>< 1 hour old}

    CACHE -->|Yes| RETURN_CACHE[Return Cached Results]
    CACHE -->|No| ALPACA_MOVERS[Fetch Alpaca Movers<br/>gainers + losers + actives]

    ALPACA_MOVERS --> MERGE[Merge Candidates]

    MERGE --> ENRICH[Enrich Missing Data]

    subgraph Enrichment
        ENRICH --> PRICE{Has Price?}
        PRICE -->|No| FETCH_QUOTE[Fetch Quote]
        PRICE -->|Yes| ATR{Has ATR?}
        FETCH_QUOTE --> ATR
        ATR -->|No| FETCH_BARS[Fetch 20-day Bars<br/>Calculate ATR]
        ATR -->|Yes| FILTER
        FETCH_BARS --> FILTER
    end

    FILTER[Apply Filters] --> F1{Valid Symbol?<br/>A-Z, dots, dashes}
    F1 -->|No| SKIP1[Skip]
    F1 -->|Yes| F2{Price in Range?<br/>$5 - $500}
    F2 -->|No| SKIP2[Skip]
    F2 -->|Yes| F3{Volatility OK?<br/>ATR/Price ≤ 10%}
    F3 -->|No| SKIP3[Skip]
    F3 -->|Yes| F4{Volume OK?<br/>≥ 200K}
    F4 -->|No| SKIP4[Skip]
    F4 -->|Yes| KEEP[Keep Candidate]

    KEEP --> LLM{LLM Ranking<br/>Enabled?}
    LLM -->|Yes| RANK[AI Re-rank Top 20]
    LLM -->|No| LIMIT[Take Top N]
    RANK --> LIMIT

    LIMIT --> SAVE[(Save to screener_results)]
```

## 7. Database Schema (ER Diagram)

```mermaid
erDiagram
    portfolio_snapshot ||--o{ holdings : contains
    portfolio_snapshot {
        int id PK
        datetime timestamp
        float total_equity
        float cash_balance
    }

    holdings {
        int id PK
        int snapshot_id FK
        string symbol
        float quantity
        float current_price
        float market_value
        float cost_basis
    }

    market_data {
        int id PK
        string symbol
        float price
        float atr
        float sma_50
        float avg_volume
        datetime updated_at
    }

    news_analysis {
        int id PK
        string symbol
        string headline
        string sentiment
        float confidence
        string implied_action
        datetime timestamp
    }

    strategy_recommendations {
        int id PK
        string symbol
        string action
        float confidence
        string reasoning
        datetime created_at
    }

    risk_decisions {
        int id PK
        int recommendation_id FK
        bool approved
        string reason
        int approved_shares
        float stop_loss
        datetime decided_at
    }

    stock_metadata {
        string symbol PK
        string company_name
        string sector
        string industry
    }

    screener_results {
        int id PK
        string symbol
        string source
        float score
        datetime screened_at
    }

    strategy_recommendations ||--o| risk_decisions : validated_by
    market_data ||--o{ strategy_recommendations : informs
    news_analysis ||--o{ strategy_recommendations : informs
    stock_metadata ||--o{ holdings : describes
```

## 8. Strategy Planner AI Flow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant SP as Strategy Planner
    participant DB as Database
    participant G as Gemini AI

    O->>SP: generate_recommendation(symbol)

    SP->>DB: Get market_data (price, ATR, SMA)
    DB-->>SP: Market context

    SP->>DB: Get news_analysis (last 72h)
    DB-->>SP: News sentiment

    SP->>DB: Get holdings (current position)
    DB-->>SP: Portfolio context

    SP->>SP: Build Chain-of-Thought prompt

    Note over SP: Prompt includes:<br/>1. Technical analysis<br/>2. News sentiment<br/>3. Portfolio context<br/>4. Risk parameters

    SP->>G: Generate recommendation
    G-->>SP: JSON response

    alt Valid JSON
        SP->>DB: Save to strategy_recommendations
        SP-->>O: {action, confidence, reasoning}
    else Parse error
        SP->>SP: Fallback to rule-based
        SP-->>O: Conservative HOLD
    end
```

## 9. Notification Flow

```mermaid
flowchart TD
    ALERT[Trade Alert] --> QUIET{Quiet Hours?<br/>9PM - 6AM}

    QUIET -->|Yes| QUEUE[Queue for Later]
    QUIET -->|No| URGENT{Urgent?}

    URGENT -->|Yes| IMSG[Send iMessage<br/>via AppleScript]
    URGENT -->|No| BATCH{Batch with<br/>others?}

    BATCH -->|Yes| ADD[Add to Batch Queue]
    BATCH -->|No| EMAIL[Send Email<br/>via Gmail SMTP]

    ADD --> TIMER{Batch Timer<br/>Expired?}
    TIMER -->|Yes| EMAIL
    TIMER -->|No| WAIT[Wait]

    IMSG --> LOG[(notification_log)]
    EMAIL --> LOG

    style IMSG fill:#c8e6c9
    style EMAIL fill:#bbdefb
```

## 10. Configuration Hierarchy

```mermaid
graph TD
    subgraph Config["config/config.yaml"]
        API[api_keys]
        RISK[risk]
        SCHEDULE[schedule]
        AI[ai]
        SCREENER[screener]
        LIMITS[limits]
    end

    subgraph Agents
        MA[Market Analyst]
        NA[News Analyst]
        SP[Strategy Planner]
        RC[Risk Controller]
        SS[Stock Screener]
        NS[Notification Specialist]
    end

    API --> MA
    API --> NA
    API --> SP
    API --> SS

    RISK --> RC
    RISK --> SS

    AI --> NA
    AI --> SP
    AI --> SS

    SCREENER --> SS

    LIMITS --> NA
    LIMITS --> MA
    LIMITS --> NS

    SCHEDULE --> NS

    ENV[".env file"] -.->|env var substitution| Config
```

## 11. REST API Architecture

```mermaid
flowchart TB
    CLIENT[Client<br/>curl / Browser / App] --> AUTH{X-API-Key<br/>Valid?}

    AUTH -->|No| REJECT[401 Unauthorized]
    AUTH -->|Yes| ROUTER[FastAPI Router]

    ROUTER --> PORTFOLIO[/portfolio/*]
    ROUTER --> MARKET[/market/*]
    ROUTER --> AGENT[/agent/*]

    PORTFOLIO --> PA[Portfolio Accountant]
    MARKET --> MA[Market Analyst]
    AGENT --> SP[Strategy Planner]
    AGENT --> TA[Trade Advisor]

    PA --> DB[(Database<br/>Turso/SQLite)]
    MA --> DB
    SP --> DB
    TA --> DB

    style AUTH fill:#fff3e0
    style REJECT fill:#ffcdd2
    style DB fill:#e3f2fd
```

## 12. Database Modes

```mermaid
flowchart TD
    APP[Application] --> CHECK{DB_MODE?}

    CHECK -->|local| LOCAL[SQLite<br/>data/agent.db]
    CHECK -->|turso| TURSO[Turso Cloud<br/>libsql://...]

    LOCAL --> CONN[get_connection<br/>context manager]
    TURSO --> CONN

    CONN --> AGENTS[All Agents]

    style LOCAL fill:#c8e6c9
    style TURSO fill:#bbdefb
```

## Reading Order Suggestion

1. **Start here**: Diagram 1 (System Overview) + Diagram 2 (Pipeline Flow)
2. **Understand timing**: Diagram 3 (Execution Modes)
3. **Deep dive**: Diagrams 4-6 for specific agent logic
4. **Data model**: Diagram 7 (Database Schema)
5. **AI integration**: Diagram 8 (Strategy Planner)
6. **Output**: Diagram 9 (Notifications)
7. **API access**: Diagram 11 (REST API)
8. **Storage**: Diagram 12 (Database Modes)
