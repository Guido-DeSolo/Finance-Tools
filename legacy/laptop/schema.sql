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
ON bars (timestamp);\



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
