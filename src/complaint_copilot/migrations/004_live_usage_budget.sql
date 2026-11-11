ALTER TABLE live_run_budgets
    ADD COLUMN max_calls INTEGER NOT NULL DEFAULT 0 CHECK (max_calls >= 0);

ALTER TABLE live_run_budgets
    ADD COLUMN used_calls INTEGER NOT NULL DEFAULT 0 CHECK (used_calls >= 0);

ALTER TABLE live_run_budgets
    ADD COLUMN max_tokens INTEGER NOT NULL DEFAULT 0 CHECK (max_tokens >= 0);

ALTER TABLE live_run_budgets
    ADD COLUMN used_tokens INTEGER NOT NULL DEFAULT 0 CHECK (used_tokens >= 0);

ALTER TABLE live_run_budgets
    ADD COLUMN max_cost_usd TEXT NOT NULL DEFAULT '0';

ALTER TABLE live_run_budgets
    ADD COLUMN used_cost_usd TEXT NOT NULL DEFAULT '0';

CREATE TABLE IF NOT EXISTS live_generation_reservations (
    approval_id TEXT NOT NULL REFERENCES live_run_budgets(approval_id),
    generation_key TEXT NOT NULL,
    reserved_tokens INTEGER NOT NULL CHECK (reserved_tokens > 0),
    reserved_cost_usd TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (approval_id, generation_key)
);
