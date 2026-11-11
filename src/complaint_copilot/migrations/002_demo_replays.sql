CREATE TABLE IF NOT EXISTS demo_replay_runs (
    idempotency_key TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
