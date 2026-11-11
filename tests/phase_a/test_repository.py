from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_copilot.repository import (
    ConcurrentUpdate,
    IdempotencyConflict,
    SQLiteRepository,
)


def test_intake_is_idempotent_and_rejects_reused_key_with_different_input(
    tmp_path: Path,
) -> None:
    repository = SQLiteRepository(tmp_path / "cases.sqlite3")
    now = datetime.now(UTC)
    intake = {
        "case_id": "case-1",
        "request_id": "request-1",
        "complaint_text": "Synthetic account access complaint.",
        "source_sample_id": None,
        "idempotency_key": "intake-key-1",
        "now": now,
    }

    case_id, created = repository.create_intake(**intake)
    repeated_id, repeated_created = repository.create_intake(**intake)

    assert (case_id, created) == ("case-1", True)
    assert (repeated_id, repeated_created) == ("case-1", False)
    assert len(repository.list_cases()) == 1
    with pytest.raises(IdempotencyConflict):
        repository.create_intake(
            **{
                **intake,
                "complaint_text": "Different synthetic complaint.",
                "case_id": "case-2",
                "request_id": "request-2",
            }
        )


def test_begin_analysis_uses_optimistic_case_version(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "cases.sqlite3")
    now = datetime.now(UTC)
    case_id, _ = repository.create_intake(
        case_id="case-1",
        request_id="request-1",
        complaint_text="Synthetic account access complaint.",
        source_sample_id=None,
        idempotency_key="intake-key-1",
        now=now,
    )

    revision = repository.begin_analysis(
        case_id=case_id,
        expected_version=1,
        analysis_id="analysis-1",
        trace_id="trace-1",
        now=now,
    )

    assert revision == 1
    assert repository.get_case(case_id)["state"] == "processing"
    with pytest.raises(ConcurrentUpdate):
        repository.begin_analysis(
            case_id=case_id,
            expected_version=1,
            analysis_id="analysis-2",
            trace_id="trace-2",
            now=now,
        )


def test_startup_recovery_marks_interrupted_case_manual_required(
    tmp_path: Path,
) -> None:
    repository = SQLiteRepository(tmp_path / "cases.sqlite3")
    now = datetime.now(UTC)
    case_id, _ = repository.create_intake(
        case_id="case-1",
        request_id="request-1",
        complaint_text="Synthetic account access complaint.",
        source_sample_id=None,
        idempotency_key="intake-key-1",
        now=now,
    )
    repository.begin_analysis(
        case_id=case_id,
        expected_version=1,
        analysis_id="analysis-1",
        trace_id="trace-1",
        now=now,
    )

    assert repository.recover_interrupted(now) == 1
    case = repository.get_case(case_id)
    assert case["state"] == "manual_required"
    assert case["failure_code"] == "process_interrupted"
    assert case["analyses"][0]["status"] == "manual_required"
