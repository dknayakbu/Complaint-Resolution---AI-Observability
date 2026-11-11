CREATE TABLE IF NOT EXISTS live_run_budgets (
    approval_id TEXT PRIMARY KEY,
    max_requests INTEGER NOT NULL CHECK (max_requests BETWEEN 1 AND 10),
    used_requests INTEGER NOT NULL DEFAULT 0 CHECK (used_requests >= 0)
);

CREATE TABLE IF NOT EXISTS live_request_reservations (
    approval_id TEXT NOT NULL REFERENCES live_run_budgets(approval_id),
    request_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (approval_id, request_key)
);
