import copy
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from complaint_copilot.contracts import (
    AnalysisCompletionEvent,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisResult,
    CostObservation,
    CostSummary,
    IncidentPriority,
    InputSizeBucket,
    RunMode,
    Severity,
    StageUsageEvent,
    TokenUsage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_synthetic_result_fixtures_match_contract_shapes() -> None:
    success = AnalysisResult.from_mapping(load_fixture("successful-two-stage.json"))
    promotion = AnalysisResult.from_mapping(load_fixture("sev3-promoted-to-sev1.json"))
    drafting_failure = AnalysisResult.from_mapping(
        load_fixture("classification-retained-drafting-failed.json")
    )

    assert success.analysis_outcome is AnalysisOutcome.COMPLETE
    assert success.classification is not None
    assert success.draft is not None
    assert promotion.classification is not None
    assert promotion.classification.model_severity is Severity.SEV3
    assert promotion.effective_severity is Severity.SEV1
    assert drafting_failure.classification is not None
    assert drafting_failure.effective_severity is Severity.SEV1
    assert drafting_failure.draft is None
    assert drafting_failure.drafting_stage.failure_code == "provider_timeout"


def test_terminal_provider_error_fixtures_match_contract_shapes() -> None:
    classification_failure = AnalysisResult.from_mapping(
        load_fixture("classification-provider-error.json")
    )
    drafting_failure = AnalysisResult.from_mapping(
        load_fixture("drafting-provider-error-retains-classification.json")
    )

    assert classification_failure.classification is None
    assert classification_failure.drafting_stage.status.value == "skipped"
    assert classification_failure.classification_stage.failure_code.value == (
        "provider_error"
    )
    assert drafting_failure.classification is not None
    assert drafting_failure.effective_severity is Severity.SEV1
    assert drafting_failure.draft is None
    assert drafting_failure.drafting_stage.failure_code.value == "provider_error"


def test_failure_codes_do_not_expand_into_provider_detail_codes() -> None:
    result = copy.deepcopy(load_fixture("classification-provider-error.json"))
    result["classification_stage"]["failure_code"] = "provider_rate_limited"

    with pytest.raises(ValueError, match="unsupported value"):
        AnalysisResult.from_mapping(result)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("classification", "model_severity"), 0),
        (("classification", "model_severity"), 4),
        (("classification", "model_severity"), True),
        (("classification", "model_severity"), 1.0),
        (("schema_version",), 2),
        (("schema_version",), True),
    ],
)
def test_result_rejects_invalid_severity_and_schema(
    path: tuple[str, ...], value: object
) -> None:
    result = copy.deepcopy(load_fixture("successful-two-stage.json"))
    target = result
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValueError):
        AnalysisResult.from_mapping(result)


def test_result_rejects_effective_severity_demotion() -> None:
    result = copy.deepcopy(load_fixture("sev3-promoted-to-sev1.json"))
    result["classification"]["model_severity"] = 1
    result["effective_severity"] = 3

    with pytest.raises(ValueError, match="cannot be demoted"):
        AnalysisResult.from_mapping(result)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("case_id", ""),
        ("analysis_id", None),
        ("request_id", ""),
        ("analysis_revision", 0),
        ("analysis_revision", True),
    ],
)
def test_result_requires_identifiers_and_positive_revision(
    key: str, value: object
) -> None:
    result = copy.deepcopy(load_fixture("successful-two-stage.json"))
    result[key] = value

    with pytest.raises(ValueError):
        AnalysisResult.from_mapping(result)


def test_result_requires_schema_version_and_identifiers() -> None:
    result = load_fixture("successful-two-stage.json")
    del result["case_id"]
    with pytest.raises(ValueError, match="case_id"):
        AnalysisResult.from_mapping(result)


def test_unknown_usage_and_cost_are_not_zero() -> None:
    unknown_usage = TokenUsage.from_mapping(
        {
            "input_tokens": None,
            "output_tokens": None,
            "provider_cached_input_tokens": None,
            "known": False,
            "unknown_reason": "provider_usage_unavailable",
        }
    )
    zero_usage = TokenUsage.from_mapping(
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "provider_cached_input_tokens": 0,
            "known": True,
            "unknown_reason": None,
        }
    )
    unknown_cost = CostObservation.from_mapping(
        {
            "amount_usd": None,
            "complete": False,
            "pricing_version": None,
            "unknown_reason": "usage_unknown",
        }
    )
    zero_cost = CostObservation.from_mapping(
        {
            "amount_usd": "0",
            "complete": True,
            "pricing_version": "fixture-prices-v1",
            "unknown_reason": None,
        }
    )

    assert unknown_usage.known is False
    assert unknown_usage.input_tokens is None
    assert zero_usage.known is True
    assert zero_usage.input_tokens == 0
    assert unknown_cost.amount_usd is None
    assert unknown_cost.complete is False
    assert zero_cost.amount_usd == 0
    assert zero_cost.complete is True


def test_unknown_usage_cannot_be_encoded_as_zero_tokens() -> None:
    with pytest.raises(ValueError, match="unknown usage"):
        TokenUsage.from_mapping(
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "provider_cached_input_tokens": None,
                "known": False,
                "unknown_reason": "provider_usage_unavailable",
            }
        )


def test_unknown_cost_cannot_be_encoded_as_complete_zero() -> None:
    with pytest.raises(ValueError, match="incomplete cost"):
        CostObservation.from_mapping(
            {
                "amount_usd": "0",
                "complete": False,
                "pricing_version": None,
                "unknown_reason": "usage_unknown",
            }
        )


def test_drafting_failure_retains_classification_and_urgency() -> None:
    result = AnalysisResult.from_mapping(
        load_fixture("classification-retained-drafting-failed.json")
    )

    assert result.analysis_outcome is AnalysisOutcome.MANUAL_REQUIRED
    assert result.classification is not None
    assert result.effective_severity is Severity.SEV1
    assert result.draft is None


def test_drafting_failure_cannot_discard_classification() -> None:
    result = copy.deepcopy(load_fixture("classification-retained-drafting-failed.json"))
    result["classification"] = None

    with pytest.raises(ValueError, match="retain classification"):
        AnalysisResult.from_mapping(result)


def test_result_rejects_oversized_draft() -> None:
    result = copy.deepcopy(load_fixture("successful-two-stage.json"))
    result["draft"] = "x" * 20_001

    with pytest.raises(ValueError, match="draft exceeds"):
        AnalysisResult.from_mapping(result)


def test_failed_classification_must_skip_drafting() -> None:
    result = copy.deepcopy(load_fixture("successful-two-stage.json"))
    result["classification"] = None
    result["effective_severity"] = None
    result["classification_stage"] = {
        "status": "failed",
        "failure_code": "classification_invalid",
    }
    result["drafting_stage"] = {"status": "skipped", "failure_code": None}
    result["draft"] = None
    result["analysis_outcome"] = "manual_required"
    result["case_state"] = "manual_required"
    result["drafting_prompt_version"] = None
    result["drafting_schema_version"] = None

    AnalysisResult.from_mapping(result)


def test_failed_classification_cannot_produce_a_draft() -> None:
    result = copy.deepcopy(load_fixture("successful-two-stage.json"))
    result["classification"] = None
    result["effective_severity"] = None
    result["classification_stage"] = {
        "status": "failed",
        "failure_code": "classification_invalid",
    }
    result["analysis_outcome"] = "manual_required"

    with pytest.raises(ValueError, match="drafting cannot succeed"):
        AnalysisResult.from_mapping(result)


@pytest.mark.parametrize(
    "ground_truth_field",
    [
        "expected_category",
        "expected_severity",
        "ground_truth_category",
        "label_version",
    ],
)
def test_agent_input_rejects_ground_truth_fields(ground_truth_field: str) -> None:
    request = {
        "complaint_text": "Synthetic account access complaint.",
        "synthetic": True,
        ground_truth_field: "accounts",
    }

    with pytest.raises(ValueError, match="agent input"):
        AnalysisRequest.from_mapping(request)


def test_agent_input_requires_synthetic_nonblank_bounded_text() -> None:
    for request in (
        {"complaint_text": " ", "synthetic": True},
        {"complaint_text": "Synthetic text.", "synthetic": False},
        {"complaint_text": "x" * 20_001, "synthetic": True},
    ):
        with pytest.raises(ValueError):
            AnalysisRequest.from_mapping(request)


def test_stage_usage_requires_identifiers_and_positive_revision() -> None:
    event = {
        "schema_version": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "event_id": "event-001",
        "case_id": "case-001",
        "analysis_id": "analysis-001",
        "analysis_revision": 1,
        "stage": "classification",
        "attempt": 1,
        "run_mode": "fixture",
        "input_size_bucket": "short",
        "requested_model": "fixture-model",
        "served_model": None,
        "prompt_version": "classification-prompt-v1",
        "policy_version": "training-policy-v1",
        "model_policy_version": "model-policy-v1",
        "succeeded": False,
        "error_category": "provider_timeout",
        "duration_ms": 0,
        "stage_schema_version": "classification-schema-v1",
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "provider_cached_input_tokens": None,
            "known": False,
            "unknown_reason": "provider_usage_unavailable",
        },
        "cost": {
            "amount_usd": None,
            "complete": False,
            "pricing_version": None,
            "unknown_reason": "usage_unknown",
        },
    }

    assert StageUsageEvent.from_mapping(event).event_id == "event-001"

    for key, value in (("event_id", ""), ("analysis_revision", 0)):
        invalid_event = copy.deepcopy(event)
        invalid_event[key] = value
        with pytest.raises(ValueError):
            StageUsageEvent.from_mapping(invalid_event)


def test_completion_event_requires_unique_stage_event_references() -> None:
    event = AnalysisCompletionEvent(
        schema_version=1,
        timestamp=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
        event_id="completion-001",
        case_id="case-001",
        analysis_id="analysis-001",
        analysis_revision=1,
        run_mode=RunMode.FIXTURE,
        input_size_bucket=InputSizeBucket.SHORT,
        policy_version="training-policy-v1",
        model_policy_version="model-policy-v1",
        analysis_outcome=AnalysisOutcome.COMPLETE,
        duration_ms=0,
        stage_event_ids=("classification-001", "drafting-001"),
        cost=CostSummary.from_mapping(
            {
                "known_subtotal_usd": "0",
                "complete": True,
                "unknown_reason": None,
            }
        ),
    )

    assert len(event.stage_event_ids) == 2
    assert IncidentPriority.P1.value == "P1"
    assert IncidentPriority.P1 != Severity.SEV1

    with pytest.raises(ValueError, match="must be unique"):
        replace(event, stage_event_ids=("duplicate", "duplicate"))
    with pytest.raises(ValueError, match="event_id"):
        replace(event, event_id="")
    with pytest.raises(ValueError, match="analysis_revision"):
        replace(event, analysis_revision=0)
    with pytest.raises(ValueError, match="UTC timestamp"):
        replace(event, timestamp=datetime.fromisoformat("2026-01-01T00:00:00"))
