"""Transactional SQLite persistence for Phase A records."""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from complaint_copilot.contracts import (
    AdjudicatedLabel,
    AnalysisCompletionEvent,
    AnalysisResult,
    AnnotationCandidate,
    FeedbackInput,
    StageUsageEvent,
)


class RepositoryError(RuntimeError):
    """Base error for explicit repository failures."""


class RecordNotFound(RepositoryError):
    pass


class ConcurrentUpdate(RepositoryError):
    pass


class IdempotencyConflict(RepositoryError):
    pass


class InvalidCaseState(RepositoryError):
    pass


class LiveBudgetExhausted(RepositoryError):
    pass


def to_wire(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_wire(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_wire(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(to_wire(value), sort_keys=True, separators=(",", ":"))


def _payload_hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class SQLiteRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if str(database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            for version, filename in (
                (1, "001_initial.sql"),
                (2, "002_demo_replays.sql"),
                (3, "003_live_run_budget.sql"),
                (4, "004_live_usage_budget.sql"),
            ):
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
                if applied is None:
                    connection.executescript(
                        (migration_dir / filename).read_text(encoding="utf-8")
                    )
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) "
                        "VALUES(?, ?)",
                        (version, datetime.now().astimezone().isoformat()),
                    )

    def reserve_live_request(
        self,
        *,
        approval_id: str,
        max_requests: int,
        max_calls: int,
        max_tokens: int,
        max_cost_usd: Decimal,
        request_key: str,
        now: datetime,
    ) -> bool:
        if not approval_id.strip() or not request_key.strip():
            raise ValueError("live approval ID and request key must be non-empty")
        if type(max_requests) is not int or not 1 <= max_requests <= 10:
            raise ValueError("live request limit must be between 1 and 10")
        if type(max_calls) is not int or not 1 <= max_calls <= 60:
            raise ValueError("live call limit must be between 1 and 60")
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError("live token limit must be positive")
        if not max_cost_usd.is_finite() or max_cost_usd <= 0:
            raise ValueError("live cost limit must be positive and finite")
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO live_run_budgets"
                "(approval_id, max_requests, used_requests, max_calls, used_calls, "
                "max_tokens, used_tokens, max_cost_usd, used_cost_usd) "
                "VALUES (?, ?, 0, ?, 0, ?, 0, ?, '0')",
                (
                    approval_id,
                    max_requests,
                    max_calls,
                    max_tokens,
                    str(max_cost_usd),
                ),
            )
            budget = connection.execute(
                "SELECT max_requests, used_requests, max_calls, max_tokens, "
                "max_cost_usd FROM live_run_budgets "
                "WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if budget is None:
                raise RepositoryError("live request budget could not be loaded")
            if (
                budget["max_requests"] != max_requests
                or budget["max_calls"] != max_calls
                or budget["max_tokens"] != max_tokens
                or budget["max_cost_usd"] != str(max_cost_usd)
            ):
                raise IdempotencyConflict(
                    "live approval ID is already bound to different budget limits"
                )
            existing = connection.execute(
                "SELECT 1 FROM live_request_reservations "
                "WHERE approval_id=? AND request_key=?",
                (approval_id, request_key),
            ).fetchone()
            if existing is not None:
                return False
            if budget["used_requests"] >= max_requests:
                raise LiveBudgetExhausted("approved live request limit is exhausted")
            connection.execute(
                "INSERT INTO live_request_reservations"
                "(approval_id, request_key, created_at) VALUES (?, ?, ?)",
                (approval_id, request_key, to_wire(now)),
            )
            connection.execute(
                "UPDATE live_run_budgets SET used_requests=used_requests+1 "
                "WHERE approval_id=?",
                (approval_id,),
            )
            return True

    def reserve_live_generation(
        self,
        *,
        approval_id: str,
        generation_key: str,
        reserved_tokens: int,
        reserved_cost_usd: Decimal,
        max_calls: int,
        max_tokens: int,
        max_cost_usd: Decimal,
        now: datetime,
    ) -> None:
        if not approval_id.strip() or not generation_key.strip():
            raise ValueError("live approval ID and generation key must be non-empty")
        if type(reserved_tokens) is not int or reserved_tokens < 1:
            raise ValueError("reserved token count must be positive")
        if not reserved_cost_usd.is_finite() or reserved_cost_usd < 0:
            raise ValueError("reserved generation cost must be finite and non-negative")
        with self._transaction() as connection:
            budget = connection.execute(
                "SELECT max_calls, used_calls, max_tokens, used_tokens, "
                "max_cost_usd, used_cost_usd FROM live_run_budgets "
                "WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if budget is None:
                raise RepositoryError("live request budget was not initialized")
            if (
                budget["max_calls"] != max_calls
                or budget["max_tokens"] != max_tokens
                or budget["max_cost_usd"] != str(max_cost_usd)
            ):
                raise IdempotencyConflict(
                    "live approval ID is already bound to different budget limits"
                )
            duplicate = connection.execute(
                "SELECT 1 FROM live_generation_reservations "
                "WHERE approval_id=? AND generation_key=?",
                (approval_id, generation_key),
            ).fetchone()
            if duplicate is not None:
                raise IdempotencyConflict(
                    "live generation attempt was already reserved"
                )

            next_tokens = budget["used_tokens"] + reserved_tokens
            next_cost = Decimal(budget["used_cost_usd"]) + reserved_cost_usd
            if budget["used_calls"] >= max_calls:
                raise LiveBudgetExhausted(
                    "approved live provider-call limit is exhausted"
                )
            if next_tokens > max_tokens:
                raise LiveBudgetExhausted("approved live token limit would be exceeded")
            if next_cost > max_cost_usd:
                raise LiveBudgetExhausted("approved live cost limit would be exceeded")

            connection.execute(
                "INSERT INTO live_generation_reservations"
                "(approval_id, generation_key, reserved_tokens, reserved_cost_usd, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    approval_id,
                    generation_key,
                    reserved_tokens,
                    str(reserved_cost_usd),
                    to_wire(now),
                ),
            )
            connection.execute(
                "UPDATE live_run_budgets SET used_calls=used_calls+1, "
                "used_tokens=?, used_cost_usd=? WHERE approval_id=?",
                (next_tokens, str(next_cost), approval_id),
            )

    def store_demo_replay(
        self,
        *,
        idempotency_key: str,
        scenario: str,
        result: Mapping[str, object],
        now: datetime,
    ) -> tuple[dict[str, object], bool]:
        encoded = _json(result)
        with self._transaction() as connection:
            prior = connection.execute(
                "SELECT scenario, result_json FROM demo_replay_runs "
                "WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if prior is not None:
                if prior["scenario"] != scenario:
                    raise IdempotencyConflict(
                        "replay idempotency key was already used for another scenario"
                    )
                return json.loads(prior["result_json"]), False
            connection.execute(
                "INSERT INTO demo_replay_runs"
                "(idempotency_key, scenario, result_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (idempotency_key, scenario, encoded, to_wire(now)),
            )
        return dict(result), True

    def create_intake(
        self,
        *,
        case_id: str,
        request_id: str,
        complaint_text: str,
        source_sample_id: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> tuple[str, bool]:
        fingerprint = _payload_hash(
            {
                "complaint_text": complaint_text,
                "source_sample_id": source_sample_id,
                "synthetic": True,
            }
        )
        with self._transaction() as connection:
            prior = connection.execute(
                "SELECT payload_hash, resource_id FROM idempotency_keys "
                "WHERE scope = 'intake' AND idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if prior is not None:
                if prior["payload_hash"] != fingerprint:
                    raise IdempotencyConflict(
                        "idempotency key was already used for a different request"
                    )
                return str(prior["resource_id"]), False

            connection.execute(
                """
                INSERT INTO cases (
                    case_id, request_id, complaint_text, synthetic, source_sample_id,
                    state, version, current_revision, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, 'received', 1, 0, ?, ?)
                """,
                (
                    case_id,
                    request_id,
                    complaint_text,
                    source_sample_id,
                    _json(now),
                    _json(now),
                ),
            )
            connection.execute(
                "INSERT INTO idempotency_keys("
                "scope, idempotency_key, payload_hash, resource_id) "
                "VALUES('intake', ?, ?, ?)",
                (idempotency_key, fingerprint, case_id),
            )
            self._audit(
                connection,
                case_id,
                None,
                "system",
                "intake_received",
                now,
                {"request_id": request_id},
            )
        return case_id, True

    def begin_analysis(
        self,
        *,
        case_id: str,
        expected_version: int,
        analysis_id: str,
        trace_id: str,
        now: datetime,
    ) -> int:
        with self._transaction() as connection:
            case = self._case_row(connection, case_id)
            if case["version"] != expected_version:
                raise ConcurrentUpdate("case version changed before processing")
            if case["state"] not in {
                "received",
                "awaiting_review",
                "manual_required",
                "approved_routed",
            }:
                raise InvalidCaseState("case is already processing")
            revision = int(case["current_revision"]) + 1
            connection.execute(
                "UPDATE cases SET state='processing', current_revision=?, "
                "version=version+1, updated_at=?, failure_code=NULL WHERE case_id=?",
                (revision, to_wire(now), case_id),
            )
            connection.execute(
                """
                INSERT INTO analysis_revisions(
                    case_id, revision, analysis_id, trace_id, status, created_at
                ) VALUES (?, ?, ?, ?, 'processing', ?)
                """,
                (case_id, revision, analysis_id, trace_id, to_wire(now)),
            )
            self._audit(
                connection,
                case_id,
                revision,
                "system",
                "analysis_started",
                now,
                {"analysis_id": analysis_id, "trace_id": trace_id},
            )
            return revision

    def save_classification(
        self,
        *,
        case_id: str,
        revision: int,
        classification: object,
        effective_severity: int,
        proposed_queue: str,
        policy_flags: tuple[str, ...],
        now: datetime,
    ) -> None:
        with self._transaction() as connection:
            self._assert_processing_revision(connection, case_id, revision)
            connection.execute(
                """
                UPDATE analysis_revisions
                SET status='classified', classification_json=?,
                    effective_severity=?, proposed_queue=?, policy_flags_json=?
                WHERE case_id=? AND revision=?
                """,
                (
                    _json(classification),
                    effective_severity,
                    proposed_queue,
                    _json(policy_flags),
                    case_id,
                    revision,
                ),
            )
            self._audit(
                connection,
                case_id,
                revision,
                "system",
                "classification_persisted",
                now,
                {
                    "model_severity": getattr(
                        getattr(classification, "model_severity", None), "value", None
                    ),
                    "effective_severity": effective_severity,
                    "policy_flags": policy_flags,
                },
            )

    def record_stage_event(self, event: StageUsageEvent) -> None:
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO stage_usage_events("
                "event_id, case_id, revision, event_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    event.event_id,
                    event.case_id,
                    event.analysis_revision,
                    _json(event),
                ),
            )

    def record_completion_event(self, event: AnalysisCompletionEvent) -> None:
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO completion_events("
                "event_id, case_id, revision, event_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    event.event_id,
                    event.case_id,
                    event.analysis_revision,
                    _json(event),
                ),
            )

    def finish_analysis(self, result: AnalysisResult, now: datetime) -> None:
        payload = _json(result)
        state = result.case_state.value
        with self._transaction() as connection:
            case = self._case_row(connection, result.case_id)
            if (
                case["state"] != "processing"
                or case["current_revision"] != result.analysis_revision
            ):
                raise ConcurrentUpdate("analysis revision is no longer current")
            connection.execute(
                "UPDATE analysis_revisions SET status=?, result_json=?, failure_code=? "
                "WHERE case_id=? AND revision=?",
                (
                    result.analysis_outcome.value,
                    payload,
                    (
                        result.classification_stage.failure_code.value
                        if result.classification_stage.failure_code is not None
                        else (
                            result.drafting_stage.failure_code.value
                            if result.drafting_stage.failure_code is not None
                            else None
                        )
                    ),
                    result.case_id,
                    result.analysis_revision,
                ),
            )
            connection.execute(
                "UPDATE cases SET state=?, version=version+1, updated_at=?, "
                "failure_code=? "
                "WHERE case_id=?",
                (
                    state,
                    to_wire(now),
                    (
                        result.drafting_stage.failure_code.value
                        if result.drafting_stage.failure_code is not None
                        else (
                            result.classification_stage.failure_code.value
                            if result.classification_stage.failure_code is not None
                            else None
                        )
                    ),
                    result.case_id,
                ),
            )
            self._audit(
                connection,
                result.case_id,
                result.analysis_revision,
                "system",
                "analysis_completed",
                now,
                {
                    "outcome": result.analysis_outcome.value,
                    "case_state": state,
                    "trace_id": result.trace_id,
                },
            )

    def mark_unexpected_failure(
        self,
        case_id: str,
        revision: int,
        failure_code: str,
        now: datetime,
    ) -> None:
        with self._transaction() as connection:
            self._assert_processing_revision(connection, case_id, revision)
            connection.execute(
                "UPDATE analysis_revisions SET status='manual_required', "
                "failure_code=? "
                "WHERE case_id=? AND revision=?",
                (failure_code, case_id, revision),
            )
            connection.execute(
                "UPDATE cases SET state='manual_required', version=version+1, "
                "updated_at=?, failure_code=? WHERE case_id=?",
                (to_wire(now), failure_code, case_id),
            )
            self._audit(
                connection,
                case_id,
                revision,
                "system",
                "processing_interrupted",
                now,
                {"failure_code": failure_code},
            )

    def recover_interrupted(self, now: datetime) -> int:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT case_id, current_revision FROM cases WHERE state='processing'"
            ).fetchall()
            for row in rows:
                case_id = str(row["case_id"])
                revision = int(row["current_revision"])
                connection.execute(
                    "UPDATE analysis_revisions SET status='manual_required', "
                    "failure_code='process_interrupted' WHERE case_id=? AND revision=?",
                    (case_id, revision),
                )
                connection.execute(
                    "UPDATE cases SET state='manual_required', version=version+1, "
                    "updated_at=?, failure_code='process_interrupted' WHERE case_id=?",
                    (to_wire(now), case_id),
                )
                self._audit(
                    connection,
                    case_id,
                    revision,
                    "system",
                    "processing_interrupted",
                    now,
                    {"failure_code": "process_interrupted"},
                )
            return len(rows)

    def apply_review(
        self,
        *,
        review_id: str,
        case_id: str,
        analysis_revision: int,
        expected_case_version: int,
        reviewer: str,
        reason: str,
        category: str,
        model_severity: int,
        effective_severity: int,
        queue: str,
        acknowledgement: str,
        now: datetime,
    ) -> dict[str, object]:
        with self._transaction() as connection:
            case = self._case_row(connection, case_id)
            if case["version"] != expected_case_version:
                raise ConcurrentUpdate("case version changed; reload before review")
            if case["state"] != "awaiting_review":
                raise InvalidCaseState("only an awaiting-review case can be approved")
            if case["current_revision"] != analysis_revision:
                raise ConcurrentUpdate(
                    "review must target the current analysis revision"
                )
            prior = connection.execute(
                "SELECT review_id FROM review_records WHERE case_id=? "
                "AND analysis_revision=?",
                (case_id, analysis_revision),
            ).fetchone()
            if prior is not None:
                raise InvalidCaseState(
                    "this analysis revision has already been reviewed"
                )

            connection.execute(
                """
                INSERT INTO review_records(
                    review_id, case_id, analysis_revision, reviewer, reason, category,
                    model_severity, effective_severity, queue, acknowledgement,
                    expected_case_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    case_id,
                    analysis_revision,
                    reviewer,
                    reason,
                    category,
                    model_severity,
                    effective_severity,
                    queue,
                    acknowledgement,
                    expected_case_version,
                    to_wire(now),
                ),
            )
            queue_entry_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO queue_entries(
                    queue_entry_id, case_id, analysis_revision, queue,
                    effective_severity, acknowledgement, review_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    queue_entry_id,
                    case_id,
                    analysis_revision,
                    queue,
                    effective_severity,
                    acknowledgement,
                    review_id,
                    to_wire(now),
                ),
            )
            connection.execute(
                "UPDATE cases SET state='approved_routed', version=version+1, "
                "updated_at=?, failure_code=NULL WHERE case_id=?",
                (to_wire(now), case_id),
            )
            self._audit(
                connection,
                case_id,
                analysis_revision,
                reviewer,
                "review_approved_and_routed",
                now,
                {
                    "review_id": review_id,
                    "reason": reason,
                    "category": category,
                    "effective_severity": effective_severity,
                    "queue": queue,
                },
            )
            return {
                "review_id": review_id,
                "queue_entry_id": queue_entry_id,
                "case_id": case_id,
                "analysis_revision": analysis_revision,
                "queue": queue,
                "effective_severity": effective_severity,
                "state": "approved_routed",
            }

    def save_feedback(
        self,
        feedback: FeedbackInput,
        *,
        feedback_id: str,
        actor: str,
        source: str,
        now: datetime,
    ) -> dict[str, object]:
        with self._transaction() as connection:
            self._case_row(connection, feedback.case_id)
            analysis = connection.execute(
                "SELECT 1 FROM analysis_revisions WHERE case_id=? AND revision=?",
                (feedback.case_id, feedback.analysis_revision),
            ).fetchone()
            if analysis is None:
                raise RecordNotFound("analysis revision not found")
            connection.execute(
                """
                INSERT INTO feedback_records(
                    feedback_id, case_id, analysis_revision, rating, note,
                    actor, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    feedback.case_id,
                    feedback.analysis_revision,
                    feedback.rating.value,
                    feedback.note,
                    actor,
                    source,
                    to_wire(now),
                ),
            )
            self._audit(
                connection,
                feedback.case_id,
                feedback.analysis_revision,
                actor,
                "feedback_recorded",
                now,
                {"feedback_id": feedback_id, "rating": feedback.rating.value},
            )
            return {
                "feedback_id": feedback_id,
                "case_id": feedback.case_id,
                "analysis_revision": feedback.analysis_revision,
                "rating": feedback.rating.value,
                "actor": actor,
                "source": source,
                "created_at": to_wire(now),
            }

    def add_annotation_candidate(
        self, annotation_id: str, candidate: AnnotationCandidate, now: datetime
    ) -> None:
        with self._transaction() as connection:
            self._case_row(connection, candidate.case_id)
            connection.execute(
                """
                INSERT INTO annotation_candidates(
                    annotation_id, case_id, analysis_revision, candidate_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id,
                    candidate.case_id,
                    candidate.analysis_revision,
                    _json(candidate),
                    candidate.status.value,
                    to_wire(now),
                ),
            )

    def merge_annotation_candidate(
        self, candidate: AnnotationCandidate, now: datetime
    ) -> str:
        with self._transaction() as connection:
            self._case_row(connection, candidate.case_id)
            existing = connection.execute(
                "SELECT annotation_id FROM annotation_candidates "
                "WHERE case_id=? AND analysis_revision=? AND status='pending' "
                "ORDER BY created_at LIMIT 1",
                (candidate.case_id, candidate.analysis_revision),
            ).fetchone()
            if existing is not None:
                annotation_id = str(existing["annotation_id"])
                connection.execute(
                    "UPDATE annotation_candidates SET candidate_json=? "
                    "WHERE annotation_id=?",
                    (_json(candidate), annotation_id),
                )
                return annotation_id
            annotation_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO annotation_candidates("
                "annotation_id, case_id, analysis_revision, candidate_json, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    annotation_id,
                    candidate.case_id,
                    candidate.analysis_revision,
                    _json(candidate),
                    candidate.status.value,
                    to_wire(now),
                ),
            )
            return annotation_id

    def adjudicate_label(
        self,
        *,
        label_id: str,
        annotation_id: str,
        label: AdjudicatedLabel,
        expected_case_version: int,
        now: datetime,
    ) -> dict[str, object]:
        with self._transaction() as connection:
            case = self._case_row(connection, label.case_id)
            if case["version"] != expected_case_version:
                raise ConcurrentUpdate(
                    "case version changed; reload before adjudication"
                )
            candidate = connection.execute(
                "SELECT status, case_id, analysis_revision FROM annotation_candidates "
                "WHERE annotation_id=?",
                (annotation_id,),
            ).fetchone()
            if candidate is None:
                raise RecordNotFound("annotation candidate not found")
            if (
                candidate["case_id"] != label.case_id
                or candidate["analysis_revision"] != label.analysis_revision
            ):
                raise ConcurrentUpdate(
                    "label must reference the candidate's exact revision"
                )
            if candidate["status"] != "pending":
                raise InvalidCaseState(
                    "annotation candidate has already been adjudicated"
                )
            prior = connection.execute(
                "SELECT label_id FROM adjudicated_labels WHERE case_id=? "
                "AND analysis_revision=? ORDER BY created_at DESC LIMIT 1",
                (label.case_id, label.analysis_revision),
            ).fetchone()
            supersedes = prior["label_id"] if prior is not None else None
            connection.execute(
                "INSERT INTO adjudicated_labels("
                "label_id, case_id, analysis_revision, label_json, "
                "supersedes_label_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    label_id,
                    label.case_id,
                    label.analysis_revision,
                    _json(label),
                    supersedes,
                    to_wire(now),
                ),
            )
            connection.execute(
                "UPDATE annotation_candidates SET status='adjudicated' "
                "WHERE annotation_id=?",
                (annotation_id,),
            )
            connection.execute(
                "UPDATE cases SET version=version+1, updated_at=? WHERE case_id=?",
                (to_wire(now), label.case_id),
            )
            self._audit(
                connection,
                label.case_id,
                label.analysis_revision,
                label.reviewer,
                "label_adjudicated",
                now,
                {"label_id": label_id, "annotation_id": annotation_id},
            )
            return {
                "label_id": label_id,
                "annotation_id": annotation_id,
                "label": to_wire(label),
                "supersedes_label_id": supersedes,
            }

    def store_alert(
        self,
        *,
        event_id: str,
        received_at: datetime,
        status: str,
        priority: str,
        name: str,
        payload: Mapping[str, object],
    ) -> bool:
        encoded = _json(payload)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM alert_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != encoded:
                    raise IdempotencyConflict(
                        "alert event ID was reused with new content"
                    )
                return False
            connection.execute(
                "INSERT INTO alert_events("
                "event_id, received_at, status, priority, name, "
                "payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, to_wire(received_at), status, priority, name, encoded),
            )
            return True

    def get_case(self, case_id: str) -> dict[str, object]:
        with self._connection() as connection:
            row = self._case_row(connection, case_id)
            return self._case_dict(connection, row)

    def list_cases(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM cases ORDER BY created_at DESC"
            ).fetchall()
            return [self._case_dict(connection, row) for row in rows]

    def list_queue(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM queue_entries ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def list_feedback(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM feedback_records ORDER BY created_at DESC"
                )
            ]

    def list_annotations(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM annotation_candidates ORDER BY created_at DESC"
            ).fetchall()
            return [
                {
                    "annotation_id": row["annotation_id"],
                    "case_id": row["case_id"],
                    "analysis_revision": row["analysis_revision"],
                    "candidate": json.loads(row["candidate_json"]),
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def list_alerts(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_id, received_at, status, priority, name, payload_json "
                "FROM alert_events ORDER BY received_at DESC"
            ).fetchall()
            return [
                {
                    "event_id": row["event_id"],
                    "received_at": row["received_at"],
                    "status": row["status"],
                    "priority": row["priority"],
                    "name": row["name"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in rows
            ]

    def list_recent_completion_events(
        self, limit: int, run_mode: str
    ) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("completion-event limit must be between 1 and 500")
        if not run_mode.strip():
            raise ValueError("completion-event run mode must be non-empty")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_json FROM completion_events "
                "WHERE json_extract(event_json, '$.run_mode')=? "
                "ORDER BY rowid DESC LIMIT ?",
                (run_mode, limit),
            ).fetchall()
            return [json.loads(row["event_json"]) for row in rows]

    def _case_row(self, connection: sqlite3.Connection, case_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM cases WHERE case_id=?", (case_id,)
        ).fetchone()
        if row is None:
            raise RecordNotFound("case not found")
        if not isinstance(row, sqlite3.Row):
            raise RepositoryError("case query returned an unexpected row type")
        return row

    def _assert_processing_revision(
        self, connection: sqlite3.Connection, case_id: str, revision: int
    ) -> None:
        case = self._case_row(connection, case_id)
        if case["state"] != "processing" or case["current_revision"] != revision:
            raise ConcurrentUpdate("case is not on the expected processing revision")

    def _case_dict(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, object]:
        case_id = str(row["case_id"])
        revisions = connection.execute(
            "SELECT revision, analysis_id, trace_id, status, classification_json, "
            "effective_severity, proposed_queue, policy_flags_json, result_json, "
            "failure_code, created_at FROM analysis_revisions "
            "WHERE case_id=? ORDER BY revision",
            (case_id,),
        ).fetchall()
        audit = connection.execute(
            "SELECT event_id, analysis_revision, actor, event_type, occurred_at, "
            "details_json FROM audit_events WHERE case_id=? "
            "ORDER BY occurred_at, event_id",
            (case_id,),
        ).fetchall()
        return {
            "case_id": case_id,
            "request_id": row["request_id"],
            "complaint_text": row["complaint_text"],
            "synthetic": bool(row["synthetic"]),
            "source_sample_id": row["source_sample_id"],
            "state": row["state"],
            "version": row["version"],
            "current_revision": row["current_revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "failure_code": row["failure_code"],
            "analyses": [
                {
                    "revision": item["revision"],
                    "analysis_id": item["analysis_id"],
                    "trace_id": item["trace_id"],
                    "status": item["status"],
                    "classification": (
                        json.loads(item["classification_json"])
                        if item["classification_json"]
                        else None
                    ),
                    "effective_severity": item["effective_severity"],
                    "proposed_queue": item["proposed_queue"],
                    "policy_flags": json.loads(item["policy_flags_json"]),
                    "result": (
                        json.loads(item["result_json"]) if item["result_json"] else None
                    ),
                    "failure_code": item["failure_code"],
                    "created_at": item["created_at"],
                }
                for item in revisions
            ],
            "audit": [
                {
                    "event_id": item["event_id"],
                    "analysis_revision": item["analysis_revision"],
                    "actor": item["actor"],
                    "event_type": item["event_type"],
                    "occurred_at": item["occurred_at"],
                    "details": json.loads(item["details_json"]),
                }
                for item in audit
            ],
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        case_id: str,
        revision: int | None,
        actor: str,
        event_type: str,
        now: datetime,
        details: Mapping[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events(event_id, case_id, analysis_revision, actor, "
            "event_type, occurred_at, details_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                case_id,
                revision,
                actor,
                event_type,
                to_wire(now),
                _json(details),
            ),
        )
