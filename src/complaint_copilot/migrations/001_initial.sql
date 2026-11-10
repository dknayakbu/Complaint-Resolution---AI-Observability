CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    complaint_text TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    source_sample_id TEXT,
    state TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    current_revision INTEGER NOT NULL DEFAULT 0 CHECK (current_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    failure_code TEXT
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    PRIMARY KEY (scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS analysis_revisions (
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    analysis_id TEXT NOT NULL UNIQUE,
    trace_id TEXT NOT NULL,
    status TEXT NOT NULL,
    classification_json TEXT,
    effective_severity INTEGER,
    proposed_queue TEXT,
    policy_flags_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (case_id, revision)
);

CREATE TABLE IF NOT EXISTS stage_usage_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    revision INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    FOREIGN KEY (case_id, revision)
        REFERENCES analysis_revisions(case_id, revision)
);

CREATE TABLE IF NOT EXISTS completion_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    revision INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    FOREIGN KEY (case_id, revision)
        REFERENCES analysis_revisions(case_id, revision)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    analysis_revision INTEGER,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_records (
    review_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    analysis_revision INTEGER NOT NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    category TEXT NOT NULL,
    model_severity INTEGER NOT NULL,
    effective_severity INTEGER NOT NULL,
    queue TEXT NOT NULL,
    acknowledgement TEXT NOT NULL,
    expected_case_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (case_id, analysis_revision)
);

CREATE TABLE IF NOT EXISTS queue_entries (
    queue_entry_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    analysis_revision INTEGER NOT NULL,
    queue TEXT NOT NULL,
    effective_severity INTEGER NOT NULL,
    acknowledgement TEXT NOT NULL,
    review_id TEXT NOT NULL UNIQUE REFERENCES review_records(review_id),
    created_at TEXT NOT NULL,
    UNIQUE (case_id, analysis_revision)
);

CREATE TABLE IF NOT EXISTS feedback_records (
    feedback_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    analysis_revision INTEGER NOT NULL,
    rating TEXT NOT NULL,
    note TEXT,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id, analysis_revision)
        REFERENCES analysis_revisions(case_id, revision)
);

CREATE TABLE IF NOT EXISTS annotation_candidates (
    annotation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    analysis_revision INTEGER NOT NULL,
    candidate_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id, analysis_revision)
        REFERENCES analysis_revisions(case_id, revision),
    UNIQUE (case_id, analysis_revision, annotation_id)
);

CREATE TABLE IF NOT EXISTS adjudicated_labels (
    label_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    analysis_revision INTEGER NOT NULL,
    label_json TEXT NOT NULL,
    supersedes_label_id TEXT REFERENCES adjudicated_labels(label_id),
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id, analysis_revision)
        REFERENCES analysis_revisions(case_id, revision)
);

CREATE TABLE IF NOT EXISTS alert_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
