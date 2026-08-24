CREATE TABLE IF NOT EXISTS bars (
    symbol       TEXT NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    open         DOUBLE PRECISION NOT NULL,
    high         DOUBLE PRECISION NOT NULL,
    low          DOUBLE PRECISION NOT NULL,
    close        DOUBLE PRECISION NOT NULL,
    volume       BIGINT NOT NULL,
    trade_count  BIGINT,
    vwap         DOUBLE PRECISION,

    PRIMARY KEY (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS bars_timestamp_idx
ON bars (timestamp);



CREATE TABLE IF NOT EXISTS news (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    headline TEXT NOT NULL,
    summary TEXT,
    author TEXT,
    source TEXT,
    url TEXT,
    symbols TEXT[],
    content TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_created_at
    ON news (created_at);

CREATE INDEX IF NOT EXISTS idx_news_symbols
    ON news USING GIN (symbols);



CREATE TABLE IF NOT EXISTS insider_trades (
    id BIGSERIAL PRIMARY KEY,

    filing_date TIMESTAMPTZ NOT NULL,
    trade_date DATE NOT NULL,

    ticker TEXT NOT NULL,
    company TEXT,
    insider TEXT,
    title TEXT,
    trade_type TEXT NOT NULL,

    price DOUBLE PRECISION,
    quantity BIGINT,
    owned BIGINT,
    ownership_change DOUBLE PRECISION,
    trade_value DOUBLE PRECISION,

    filing_url TEXT,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        filing_url,
        ticker,
        insider,
        trade_date,
        trade_type,
        quantity
    )
);

CREATE INDEX IF NOT EXISTS insider_ticker_idx
ON insider_trades (ticker);

CREATE INDEX IF NOT EXISTS insider_filing_date_idx
ON insider_trades (filing_date);

CREATE INDEX IF NOT EXISTS insider_trade_date_idx
ON insider_trades (trade_date);


CREATE OR REPLACE VIEW insider_events AS
SELECT
    ticker,
    filing_date::date AS filing_day,
    MIN(trade_date) AS first_trade_date,
    MAX(trade_date) AS last_trade_date,

    COUNT(*) FILTER (
        WHERE trade_type = 'P - Purchase'
    ) AS purchase_count,

    COUNT(DISTINCT insider) FILTER (
        WHERE trade_type = 'P - Purchase'
          AND insider IS NOT NULL
    ) AS unique_buyers,

    ARRAY_AGG(DISTINCT insider ORDER BY insider) FILTER (
        WHERE trade_type = 'P - Purchase'
          AND insider IS NOT NULL
    ) AS purchase_insiders,

    COALESCE(
        SUM(trade_value) FILTER (
            WHERE trade_type = 'P - Purchase'
        ),
        0
    ) AS total_purchase_value,

    COALESCE(
        ABS(SUM(trade_value) FILTER (
            WHERE trade_type LIKE 'S - Sale%'
        )),
        0
    ) AS total_sale_value,

    BOOL_OR(
        trade_type = 'P - Purchase'
        AND title ILIKE '%CEO%'
    ) AS ceo_participated,

    BOOL_OR(
        trade_type = 'P - Purchase'
        AND title ILIKE '%CFO%'
    ) AS cfo_participated,

    BOOL_OR(
        trade_type = 'P - Purchase'
        AND (
            title ILIKE '%Director%'
            OR title ILIKE '%Dir%'
        )
    ) AS director_participated,

    MAX(ownership_change) FILTER (
        WHERE trade_type = 'P - Purchase'
    ) AS max_ownership_change,

    COUNT(DISTINCT insider) FILTER (
        WHERE trade_type = 'P - Purchase'
          AND insider IS NOT NULL
    ) >= 2 AS cluster,

    COUNT(DISTINCT filing_url) FILTER (
        WHERE filing_url IS NOT NULL
    ) AS filing_count

FROM insider_trades
GROUP BY
    ticker,
    filing_date::date;


CREATE OR REPLACE VIEW insider_features_30d AS
SELECT
    t1.ticker,
    t1.filing_date,

    COUNT(*) FILTER (
        WHERE t2.trade_type = 'P - Purchase'
    ) AS buy_count_30d,

    COUNT(DISTINCT t2.insider) FILTER (
        WHERE t2.trade_type = 'P - Purchase'
    ) AS unique_buyers_30d,

    COALESCE(
        SUM(t2.trade_value) FILTER (
            WHERE t2.trade_type = 'P - Purchase'
        ),
        0
    ) AS buy_value_30d,

    COALESCE(
        ABS(
            SUM(t2.trade_value) FILTER (
                WHERE t2.trade_type LIKE 'S - Sale%'
            )
        ),
        0
    ) AS sell_value_30d,

    COALESCE(
        SUM(t2.trade_value),
        0
    ) AS net_insider_flow_30d,

    MAX(t2.ownership_change) FILTER (
        WHERE t2.trade_type = 'P - Purchase'
    ) AS max_buy_ownership_change_30d,

    BOOL_OR(
        t2.trade_type = 'P - Purchase'
        AND t2.title ILIKE '%CEO%'
    ) AS ceo_buy_30d,

    BOOL_OR(
        t2.trade_type = 'P - Purchase'
        AND t2.title ILIKE '%CFO%'
    ) AS cfo_buy_30d,

    BOOL_OR(
        t2.trade_type = 'P - Purchase'
        AND (
            t2.title ILIKE '%Dir%'
            OR t2.title ILIKE '%Director%'
        )
    ) AS director_buy_30d,

    (
        COUNT(DISTINCT t2.insider) FILTER (
            WHERE t2.trade_type = 'P - Purchase'
        ) >= 2
    ) AS cluster_buy_30d

FROM insider_trades t1

JOIN insider_trades t2
    ON t1.ticker = t2.ticker
    AND t2.filing_date <= t1.filing_date
    AND t2.filing_date >
        t1.filing_date - INTERVAL '30 days'

GROUP BY
    t1.ticker,
    t1.filing_date;



CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    trade_count BIGINT,
    vwap DOUBLE PRECISION,

    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS daily_bars_symbol_idx
ON daily_bars (symbol);

CREATE INDEX IF NOT EXISTS daily_bars_date_idx
ON daily_bars (date);

CREATE TABLE IF NOT EXISTS daily_bars_sip (
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    trade_count BIGINT,
    vwap DOUBLE PRECISION,

    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS daily_bars_sip_symbol_idx
ON daily_bars_sip (symbol);

CREATE INDEX IF NOT EXISTS daily_bars_sip_date_idx
ON daily_bars_sip (date);

CREATE TABLE IF NOT EXISTS watchlist_scores (
    symbol TEXT NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    insider_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    news_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    market_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_score DOUBLE PRECISION NOT NULL DEFAULT 0,

    buy_count_30d INTEGER NOT NULL DEFAULT 0,
    unique_buyers_30d INTEGER NOT NULL DEFAULT 0,
    buy_value_30d DOUBLE PRECISION NOT NULL DEFAULT 0,
    sell_value_30d DOUBLE PRECISION NOT NULL DEFAULT 0,

    ceo_buy_30d BOOLEAN NOT NULL DEFAULT FALSE,
    cfo_buy_30d BOOLEAN NOT NULL DEFAULT FALSE,
    cluster_buy_30d BOOLEAN NOT NULL DEFAULT FALSE,

    news_1d INTEGER NOT NULL DEFAULT 0,
    news_7d INTEGER NOT NULL DEFAULT 0,
    news_30d INTEGER NOT NULL DEFAULT 0,
    news_90d INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (symbol, scored_at)
);

ALTER TABLE watchlist_scores
ADD COLUMN IF NOT EXISTS news_90d INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS watchlist_scores_total_idx
ON watchlist_scores (total_score DESC);

CREATE INDEX IF NOT EXISTS watchlist_scores_symbol_idx
ON watchlist_scores (symbol);

CREATE TABLE IF NOT EXISTS agent_analyses (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    stance TEXT NOT NULL CHECK (stance IN ('bullish', 'bearish', 'neutral')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    time_horizon TEXT NOT NULL CHECK (time_horizon IN ('1d', '5d', '20d', '60d')),
    action TEXT NOT NULL CHECK (
        action IN ('consider_long', 'consider_short', 'watch', 'avoid')
    ),
    insider_interpretation TEXT NOT NULL CHECK (length(trim(insider_interpretation)) > 0),
    news_interpretation TEXT NOT NULL CHECK (length(trim(news_interpretation)) > 0),
    market_interpretation TEXT NOT NULL CHECK (length(trim(market_interpretation)) > 0),
    thesis TEXT NOT NULL CHECK (length(trim(thesis)) > 0),
    bear_case JSONB NOT NULL CHECK (jsonb_typeof(bear_case) = 'array'),
    catalysts JSONB NOT NULL CHECK (jsonb_typeof(catalysts) = 'array'),
    invalidation_conditions JSONB NOT NULL CHECK (
        jsonb_typeof(invalidation_conditions) = 'array'
    ),
    evidence_refs JSONB NOT NULL CHECK (jsonb_typeof(evidence_refs) = 'object'),
    evidence_summary JSONB NOT NULL CHECK (jsonb_typeof(evidence_summary) = 'object'),
    packet JSONB NOT NULL CHECK (jsonb_typeof(packet) = 'object'),
    raw_response TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_analyses_symbol_analyzed_idx
ON agent_analyses (symbol, analyzed_at DESC);
