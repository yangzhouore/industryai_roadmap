-- Additive only. Existing editions, articles and revision history are untouched.
CREATE TABLE automation_runs (
    id TEXT PRIMARY KEY,
    issue_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT
);
CREATE INDEX automation_runs_date ON automation_runs(issue_date, started_at);

CREATE TABLE api_requests (
    id TEXT PRIMARY KEY,
    month TEXT NOT NULL CHECK(month ~ '^[0-9]{4}-[0-9]{2}$'),
    run_id TEXT,
    stage TEXT NOT NULL,
    model TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt >= 0),
    status TEXT NOT NULL CHECK(status IN ('reserved', 'measured')),
    reserved_usd NUMERIC(24,12) NOT NULL CHECK(reserved_usd >= 0),
    estimated_usd NUMERIC(24,12) NOT NULL CHECK(estimated_usd >= 0),
    usage JSONB,
    response_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX api_requests_month ON api_requests(month, created_at);

CREATE TABLE automation_events (
    event_key TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL
);

CREATE TABLE automation_cache (
    cache_key TEXT PRIMARY KEY,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
