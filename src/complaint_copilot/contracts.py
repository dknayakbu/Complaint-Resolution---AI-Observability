"""Typed records shared by the Complaint Resolution Co-Pilot phases."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum, IntEnum, StrEnum
from typing import Literal, Protocol

SchemaVersion = Literal[1]
MAX_COMPLAINT_TEXT_LENGTH = 20_000
MAX_EVIDENCE_QUOTE_LENGTH = 2_000
MAX_DECISION_SUMMARY_LENGTH = 4_000
MAX_DRAFT_LENGTH = 20_000
MAX_FEEDBACK_NOTE_LENGTH = 2_000
MAX_EVALUATION_FINDING_LENGTH = 2_000
MAX_POLICY_REASON_LENGTH = 500


class ContractViolation(ValueError):
    """Raised when a record does not satisfy the shared contract."""


class Severity(IntEnum):
    SEV1 = 1
    SEV2 = 2
    SEV3 = 3


class Category(StrEnum):
    CARDS_PAYMENTS = "cards_payments"
    ACCOUNTS = "accounts"
    FRAUD_SCAMS = "fraud_scams"
    LENDING = "lending"
    SERVICE_ACCESS = "service_access"
    DISCRIMINATION = "discrimination"
    OTHER = "other"


class QueueKey(StrEnum):
    CARDS_PAYMENTS = "cards_payments"
    ACCOUNTS = "accounts"
    FRAUD_SCAMS = "fraud_scams"
    LENDING = "lending"
    SERVICE_ACCESS = "service_access"
    DISCRIMINATION = "discrimination"
    OTHER = "other"


class IncidentPriority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class RunMode(StrEnum):
    DEMO = "demo"
    FIXTURE = "fixture"
    EVALUATION = "evaluation"
    FAULT = "fault"
    EXPERIMENT = "experiment"


class Stage(StrEnum):
    CLASSIFICATION = "classification"
    DRAFTING = "drafting"
    EVALUATION = "evaluation"


class AnalysisOutcome(StrEnum):
    COMPLETE = "complete"
    MANUAL_REQUIRED = "manual_required"


class CaseState(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    MANUAL_REQUIRED = "manual_required"
    APPROVED_ROUTED = "approved_routed"


class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class FailureCode(StrEnum):
    CLASSIFICATION_INVALID = "classification_invalid"
    DRAFTING_INVALID = "drafting_invalid"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_ERROR = "provider_error"


class InputSizeBucket(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class EvaluationSource(StrEnum):
    ONLINE_RULE = "online_rule"
    OFFLINE_LABEL = "offline_label"
    OPTIONAL_JUDGE = "optional_judge"


class EvaluationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class AnnotationStatus(StrEnum):
    PENDING = "pending"
    ADJUDICATED = "adjudicated"


def _as_mapping(value: object, record_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractViolation(f"{record_name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{record_name} keys must be strings")
    return value


def _check_fields(
    value: Mapping[str, object],
    record_name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = required - set(value)
    extra = set(value) - allowed
    if missing:
        raise ContractViolation(
            f"{record_name} is missing required field(s): {', '.join(sorted(missing))}"
        )
    if extra:
        raise ContractViolation(
            f"{record_name} has unknown field(s): {', '.join(sorted(extra))}"
        )


def _text(value: object, field: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{field} must be non-empty text")
    if maximum is not None and len(value) > maximum:
        raise ContractViolation(f"{field} exceeds its maximum length of {maximum}")
    return value


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ContractViolation(f"{field} must be a boolean")
    return value


def _integer(value: object, field: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ContractViolation(f"{field} must be an integer >= {minimum}")
    return value


def _enum[T: Enum](enum_type: type[T], value: object, field: str) -> T:
    if isinstance(value, enum_type):
        return value
    if enum_type is Severity and type(value) is not int:
        raise ContractViolation(f"{field} must be a severity from 1 through 3")
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ContractViolation(
            f"{field} has an unsupported value: {value!r}"
        ) from error


def _require_enum[T: Enum](enum_type: type[T], value: object, field: str) -> T:
    if not isinstance(value, enum_type):
        raise ContractViolation(f"{field} must be a {enum_type.__name__}")
    return value


def _schema_version(value: object) -> SchemaVersion:
    if type(value) is not int or value != 1:
        raise ContractViolation("schema_version must be the integer 1")
    return 1


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ContractViolation(f"{field} must be a decimal string or Decimal")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ContractViolation(f"{field} must be a valid decimal") from error
    if not amount.is_finite() or amount < 0:
        raise ContractViolation(f"{field} must be finite and non-negative")
    return amount


def _utc_timestamp(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractViolation(f"{field} must be a timezone-aware UTC timestamp")
    return value.astimezone(UTC)


def _parse_utc_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractViolation(f"{field} must be an ISO-8601 UTC timestamp") from error
    return _utc_timestamp(timestamp, field)


@dataclass(frozen=True)
class AnalysisRequest:
    complaint_text: str
    synthetic: bool
    source_sample_id: str | None = None

    def __post_init__(self) -> None:
        _text(
            self.complaint_text,
            "complaint_text",
            maximum=MAX_COMPLAINT_TEXT_LENGTH,
        )
        if _boolean(self.synthetic, "synthetic") is not True:
            raise ContractViolation("only synthetic analysis input is accepted")
        _optional_text(self.source_sample_id, "source_sample_id")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AnalysisRequest":
        mapping = _as_mapping(value, "agent input")
        prohibited = {
            key
            for key in mapping
            if key in {"expected", "ground_truth", "label"}
            or key.startswith(("expected_", "ground_truth_", "label_"))
        }
        if prohibited:
            raise ContractViolation(
                "ground-truth fields are forbidden in agent input: "
                + ", ".join(sorted(prohibited))
            )
        _check_fields(
            mapping,
            "agent input",
            {"complaint_text", "synthetic"},
            {"source_sample_id"},
        )
        return cls(
            complaint_text=_text(
                mapping["complaint_text"],
                "complaint_text",
                maximum=MAX_COMPLAINT_TEXT_LENGTH,
            ),
            synthetic=_boolean(mapping["synthetic"], "synthetic"),
            source_sample_id=_optional_text(
                mapping.get("source_sample_id"), "source_sample_id"
            ),
        )


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int
    quote: str

    def __post_init__(self) -> None:
        start = _integer(self.start, "evidence.start", minimum=0)
        end = _integer(self.end, "evidence.end", minimum=1)
        quote = _text(self.quote, "evidence.quote", maximum=MAX_EVIDENCE_QUOTE_LENGTH)
        if end <= start or end - start != len(quote):
            raise ContractViolation(
                "evidence offsets must match the quoted span length"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "EvidenceSpan":
        mapping = _as_mapping(value, "evidence span")
        _check_fields(mapping, "evidence span", {"start", "end", "quote"})
        return cls(
            start=_integer(mapping["start"], "evidence.start", minimum=0),
            end=_integer(mapping["end"], "evidence.end", minimum=1),
            quote=_text(
                mapping["quote"],
                "evidence.quote",
                maximum=MAX_EVIDENCE_QUOTE_LENGTH,
            ),
        )


@dataclass(frozen=True)
class Classification:
    category: Category
    model_severity: Severity
    evidence: tuple[EvidenceSpan, ...]
    decision_summary: str

    def __post_init__(self) -> None:
        _require_enum(Category, self.category, "category")
        _require_enum(Severity, self.model_severity, "model_severity")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, EvidenceSpan) for item in self.evidence
        ):
            raise ContractViolation("evidence must be a tuple of EvidenceSpan records")
        _text(
            self.decision_summary,
            "decision_summary",
            maximum=MAX_DECISION_SUMMARY_LENGTH,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "Classification":
        mapping = _as_mapping(value, "classification")
        _check_fields(
            mapping,
            "classification",
            {"category", "model_severity", "evidence", "decision_summary"},
        )
        raw_evidence = mapping["evidence"]
        if not isinstance(raw_evidence, (list, tuple)):
            raise ContractViolation("evidence must be a sequence")
        return cls(
            category=_enum(Category, mapping["category"], "category"),
            model_severity=_enum(Severity, mapping["model_severity"], "model_severity"),
            evidence=tuple(EvidenceSpan.from_mapping(item) for item in raw_evidence),
            decision_summary=_text(
                mapping["decision_summary"],
                "decision_summary",
                maximum=MAX_DECISION_SUMMARY_LENGTH,
            ),
        )


@dataclass(frozen=True)
class StageOutcomeRecord:
    status: StageStatus
    failure_code: FailureCode | None

    def __post_init__(self) -> None:
        _require_enum(StageStatus, self.status, "stage.status")
        if self.failure_code is not None:
            _require_enum(FailureCode, self.failure_code, "stage.failure_code")
        if (self.status is StageStatus.FAILED) != (self.failure_code is not None):
            raise ContractViolation(
                "failure_code must be present only for a failed stage"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "StageOutcomeRecord":
        mapping = _as_mapping(value, "stage outcome")
        _check_fields(mapping, "stage outcome", {"status", "failure_code"})
        raw_failure = mapping["failure_code"]
        return cls(
            status=_enum(StageStatus, mapping["status"], "stage.status"),
            failure_code=(
                _enum(FailureCode, raw_failure, "stage.failure_code")
                if raw_failure is not None
                else None
            ),
        )


@dataclass(frozen=True)
class CostSummary:
    known_subtotal_usd: Decimal
    complete: bool
    unknown_reason: str | None

    def __post_init__(self) -> None:
        _decimal(self.known_subtotal_usd, "known_subtotal_usd")
        complete = _boolean(self.complete, "cost.complete")
        reason = _optional_text(self.unknown_reason, "cost.unknown_reason")
        if complete and reason is not None:
            raise ContractViolation("complete cost cannot have an unknown reason")
        if not complete and reason is None:
            raise ContractViolation("incomplete cost requires an unknown reason")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CostSummary":
        mapping = _as_mapping(value, "cost summary")
        _check_fields(
            mapping,
            "cost summary",
            {"known_subtotal_usd", "complete", "unknown_reason"},
        )
        raw_reason = mapping["unknown_reason"]
        return cls(
            known_subtotal_usd=_decimal(
                mapping["known_subtotal_usd"], "known_subtotal_usd"
            ),
            complete=_boolean(mapping["complete"], "cost.complete"),
            unknown_reason=_optional_text(raw_reason, "cost.unknown_reason"),
        )


@dataclass(frozen=True)
class AnalysisResult:
    schema_version: SchemaVersion
    case_id: str
    analysis_id: str
    request_id: str
    analysis_revision: int
    run_mode: RunMode
    analysis_outcome: AnalysisOutcome
    case_state: CaseState
    trace_id: str
    policy_version: str
    model_policy_version: str
    classification_prompt_version: str | None
    classification_schema_version: str | None
    drafting_prompt_version: str | None
    drafting_schema_version: str | None
    classification: Classification | None
    effective_severity: Severity | None
    draft: str | None
    classification_stage: StageOutcomeRecord
    drafting_stage: StageOutcomeRecord
    cost: CostSummary

    def __post_init__(self) -> None:
        _schema_version(self.schema_version)
        _text(self.case_id, "case_id")
        _text(self.analysis_id, "analysis_id")
        _text(self.request_id, "request_id")
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _require_enum(RunMode, self.run_mode, "run_mode")
        _require_enum(AnalysisOutcome, self.analysis_outcome, "analysis_outcome")
        _require_enum(CaseState, self.case_state, "case_state")
        _text(self.trace_id, "trace_id")
        _text(self.policy_version, "policy_version")
        _text(self.model_policy_version, "model_policy_version")
        _optional_text(
            self.classification_prompt_version, "classification_prompt_version"
        )
        _optional_text(
            self.classification_schema_version, "classification_schema_version"
        )
        _optional_text(self.drafting_prompt_version, "drafting_prompt_version")
        _optional_text(self.drafting_schema_version, "drafting_schema_version")

        if not isinstance(
            self.classification_stage, StageOutcomeRecord
        ) or not isinstance(self.drafting_stage, StageOutcomeRecord):
            raise ContractViolation("stage outcomes must be StageOutcomeRecord records")
        classification_succeeded = (
            self.classification_stage.status is StageStatus.SUCCEEDED
        )
        if self.classification_stage.status is not StageStatus.SKIPPED:
            _text(
                self.classification_prompt_version,
                "classification_prompt_version",
            )
            _text(
                self.classification_schema_version,
                "classification_schema_version",
            )
        if classification_succeeded:
            if self.classification is None or self.effective_severity is None:
                raise ContractViolation(
                    "successful classification must retain classification "
                    "and effective severity"
                )
            if not isinstance(self.classification, Classification):
                raise ContractViolation(
                    "classification must be a Classification record"
                )
            _require_enum(Severity, self.effective_severity, "effective_severity")
            if self.effective_severity > self.classification.model_severity:
                raise ContractViolation(
                    "effective severity cannot be demoted below model severity"
                )
        elif self.classification is not None or self.effective_severity is not None:
            raise ContractViolation(
                "classification data requires a successful classification stage"
            )

        drafting_status = self.drafting_stage.status
        if drafting_status is StageStatus.SUCCEEDED:
            if not classification_succeeded:
                raise ContractViolation(
                    "drafting cannot succeed without successful classification"
                )
            _text(self.draft, "draft", maximum=MAX_DRAFT_LENGTH)
            _text(self.drafting_prompt_version, "drafting_prompt_version")
            _text(self.drafting_schema_version, "drafting_schema_version")
        elif drafting_status is StageStatus.FAILED:
            if not classification_succeeded or self.classification is None:
                raise ContractViolation(
                    "failed drafting must retain classification and urgency"
                )
            if self.draft is not None:
                raise ContractViolation("failed drafting cannot contain a draft")
            _text(self.drafting_prompt_version, "drafting_prompt_version")
            _text(self.drafting_schema_version, "drafting_schema_version")
        else:
            if classification_succeeded:
                raise ContractViolation(
                    "drafting may be skipped only when classification did not succeed"
                )
            if (
                self.draft is not None
                or self.drafting_prompt_version is not None
                or self.drafting_schema_version is not None
            ):
                raise ContractViolation("skipped drafting cannot contain draft output")

        both_stages_succeeded = (
            classification_succeeded and drafting_status is StageStatus.SUCCEEDED
        )
        if (self.analysis_outcome is AnalysisOutcome.COMPLETE) != both_stages_succeeded:
            raise ContractViolation(
                "complete outcome requires both stages; partial outcomes require "
                "manual_required"
            )
        expected_case_state = (
            CaseState.AWAITING_REVIEW
            if self.analysis_outcome is AnalysisOutcome.COMPLETE
            else CaseState.MANUAL_REQUIRED
        )
        if self.case_state is not expected_case_state:
            raise ContractViolation("case_state must match the analysis outcome")
        if not isinstance(self.cost, CostSummary):
            raise ContractViolation("cost must be a CostSummary record")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AnalysisResult":
        mapping = _as_mapping(value, "analysis result")
        _check_fields(
            mapping,
            "analysis result",
            {
                "schema_version",
                "case_id",
                "analysis_id",
                "request_id",
                "analysis_revision",
                "run_mode",
                "analysis_outcome",
                "case_state",
                "trace_id",
                "policy_version",
                "model_policy_version",
                "classification_prompt_version",
                "classification_schema_version",
                "drafting_prompt_version",
                "drafting_schema_version",
                "classification",
                "effective_severity",
                "draft",
                "classification_stage",
                "drafting_stage",
                "cost",
            },
        )
        raw_classification = mapping["classification"]
        raw_effective_severity = mapping["effective_severity"]
        raw_draft = mapping["draft"]
        return cls(
            schema_version=_schema_version(mapping["schema_version"]),
            case_id=_text(mapping["case_id"], "case_id"),
            analysis_id=_text(mapping["analysis_id"], "analysis_id"),
            request_id=_text(mapping["request_id"], "request_id"),
            analysis_revision=_integer(
                mapping["analysis_revision"], "analysis_revision", minimum=1
            ),
            run_mode=_enum(RunMode, mapping["run_mode"], "run_mode"),
            analysis_outcome=_enum(
                AnalysisOutcome, mapping["analysis_outcome"], "analysis_outcome"
            ),
            case_state=_enum(CaseState, mapping["case_state"], "case_state"),
            trace_id=_text(mapping["trace_id"], "trace_id"),
            policy_version=_text(mapping["policy_version"], "policy_version"),
            model_policy_version=_text(
                mapping["model_policy_version"], "model_policy_version"
            ),
            classification_prompt_version=_optional_text(
                mapping["classification_prompt_version"],
                "classification_prompt_version",
            ),
            classification_schema_version=_optional_text(
                mapping["classification_schema_version"],
                "classification_schema_version",
            ),
            drafting_prompt_version=_optional_text(
                mapping["drafting_prompt_version"], "drafting_prompt_version"
            ),
            drafting_schema_version=_optional_text(
                mapping["drafting_schema_version"], "drafting_schema_version"
            ),
            classification=(
                Classification.from_mapping(
                    _as_mapping(raw_classification, "classification")
                )
                if raw_classification is not None
                else None
            ),
            effective_severity=(
                _enum(Severity, raw_effective_severity, "effective_severity")
                if raw_effective_severity is not None
                else None
            ),
            draft=_optional_text(raw_draft, "draft"),
            classification_stage=StageOutcomeRecord.from_mapping(
                _as_mapping(mapping["classification_stage"], "classification_stage")
            ),
            drafting_stage=StageOutcomeRecord.from_mapping(
                _as_mapping(mapping["drafting_stage"], "drafting_stage")
            ),
            cost=CostSummary.from_mapping(_as_mapping(mapping["cost"], "cost")),
        )


@dataclass(frozen=True)
class AnalysisCompletionEvent:
    schema_version: SchemaVersion
    timestamp: datetime
    event_id: str
    case_id: str
    analysis_id: str
    analysis_revision: int
    run_mode: RunMode
    input_size_bucket: InputSizeBucket
    policy_version: str
    model_policy_version: str
    analysis_outcome: AnalysisOutcome
    duration_ms: int
    stage_event_ids: tuple[str, ...]
    cost: CostSummary

    def __post_init__(self) -> None:
        _schema_version(self.schema_version)
        _utc_timestamp(self.timestamp, "timestamp")
        for field in ("event_id", "case_id", "analysis_id"):
            _text(getattr(self, field), field)
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _require_enum(RunMode, self.run_mode, "run_mode")
        _require_enum(InputSizeBucket, self.input_size_bucket, "input_size_bucket")
        _text(self.policy_version, "policy_version")
        _text(self.model_policy_version, "model_policy_version")
        _require_enum(AnalysisOutcome, self.analysis_outcome, "analysis_outcome")
        _integer(self.duration_ms, "duration_ms", minimum=0)
        if not isinstance(self.stage_event_ids, tuple) or not self.stage_event_ids:
            raise ContractViolation("completion event requires stage event references")
        event_ids = tuple(
            _text(event_id, "stage_event_id") for event_id in self.stage_event_ids
        )
        if len(set(event_ids)) != len(event_ids):
            raise ContractViolation("stage event references must be unique")
        if not isinstance(self.cost, CostSummary):
            raise ContractViolation("cost must be a CostSummary record")


@dataclass(frozen=True)
class EvaluationScore:
    name: str
    value: Decimal | None

    def __post_init__(self) -> None:
        _text(self.name, "score.name")
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ContractViolation("score.value must be a finite Decimal or null")


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: SchemaVersion
    case_id: str
    analysis_id: str
    analysis_revision: int
    evaluator_version: str
    rubric_version: str
    source: EvaluationSource
    status: EvaluationStatus
    findings: tuple[str, ...]
    scores: tuple[EvaluationScore, ...]
    reason_code: str | None

    def __post_init__(self) -> None:
        _schema_version(self.schema_version)
        _text(self.case_id, "case_id")
        _text(self.analysis_id, "analysis_id")
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _text(self.evaluator_version, "evaluator_version")
        _text(self.rubric_version, "rubric_version")
        _require_enum(EvaluationSource, self.source, "evaluation.source")
        _require_enum(EvaluationStatus, self.status, "evaluation.status")
        if not isinstance(self.findings, tuple):
            raise ContractViolation("findings must be a tuple")
        for finding in self.findings:
            _text(finding, "finding", maximum=MAX_EVALUATION_FINDING_LENGTH)
        if not isinstance(self.scores, tuple) or any(
            not isinstance(score, EvaluationScore) for score in self.scores
        ):
            raise ContractViolation("scores must be a tuple of EvaluationScore records")
        reason = _optional_text(self.reason_code, "reason_code")
        if self.status is EvaluationStatus.UNKNOWN and reason is None:
            raise ContractViolation("unknown evaluation requires a reason code")


@dataclass(frozen=True)
class FeedbackInput:
    case_id: str
    analysis_revision: int
    rating: FeedbackRating
    note: str | None = None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _require_enum(FeedbackRating, self.rating, "feedback.rating")
        if self.note is not None:
            _text(self.note, "feedback.note", maximum=MAX_FEEDBACK_NOTE_LENGTH)


@dataclass(frozen=True)
class SignalReference:
    source: str
    reference_id: str
    reason_code: str

    def __post_init__(self) -> None:
        _text(self.source, "signal.source")
        _text(self.reference_id, "signal.reference_id")
        _text(self.reason_code, "signal.reason_code")


@dataclass(frozen=True)
class AnnotationCandidate:
    case_id: str
    analysis_revision: int
    signals: tuple[SignalReference, ...]
    priority: str
    evidence_links: tuple[str, ...]
    status: AnnotationStatus

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        if not isinstance(self.signals, tuple) or not self.signals:
            raise ContractViolation("annotation candidate requires signal references")
        if any(not isinstance(signal, SignalReference) for signal in self.signals):
            raise ContractViolation("signals must be SignalReference records")
        if len(set(self.signals)) != len(self.signals):
            raise ContractViolation("annotation signal references must be unique")
        _text(self.priority, "annotation priority")
        if not isinstance(self.evidence_links, tuple):
            raise ContractViolation("evidence_links must be a tuple")
        for evidence_link in self.evidence_links:
            _text(evidence_link, "evidence_link")
        _require_enum(AnnotationStatus, self.status, "annotation.status")


@dataclass(frozen=True)
class AdjudicatedLabel:
    case_id: str
    analysis_revision: int
    category: Category
    severity: Severity
    queue: QueueKey
    draft_rubric_assessment: str
    reviewer: str
    reason: str
    label_version: str
    supersedes_label_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _require_enum(Category, self.category, "category")
        _require_enum(Severity, self.severity, "severity")
        _require_enum(QueueKey, self.queue, "queue")
        for field in (
            "draft_rubric_assessment",
            "reviewer",
            "reason",
            "label_version",
        ):
            _text(getattr(self, field), field)
        _optional_text(self.supersedes_label_id, "supersedes_label_id")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    provider_cached_input_tokens: int | None
    known: bool
    unknown_reason: str | None

    def __post_init__(self) -> None:
        known = _boolean(self.known, "usage.known")
        reason = _optional_text(self.unknown_reason, "usage.unknown_reason")
        token_values = (
            self.input_tokens,
            self.output_tokens,
            self.provider_cached_input_tokens,
        )
        if known:
            if self.input_tokens is None or self.output_tokens is None:
                raise ContractViolation("known usage requires input and output tokens")
            if reason is not None:
                raise ContractViolation("known usage cannot have an unknown reason")
            for value in token_values:
                if value is not None:
                    _integer(value, "usage token count", minimum=0)
        elif any(value is not None for value in token_values) or reason is None:
            raise ContractViolation(
                "unknown usage requires null token counts and an unknown reason"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "TokenUsage":
        mapping = _as_mapping(value, "token usage")
        _check_fields(
            mapping,
            "token usage",
            {
                "input_tokens",
                "output_tokens",
                "provider_cached_input_tokens",
                "known",
                "unknown_reason",
            },
        )
        return cls(
            input_tokens=_optional_token_count(mapping["input_tokens"], "input_tokens"),
            output_tokens=_optional_token_count(
                mapping["output_tokens"], "output_tokens"
            ),
            provider_cached_input_tokens=_optional_token_count(
                mapping["provider_cached_input_tokens"],
                "provider_cached_input_tokens",
            ),
            known=_boolean(mapping["known"], "usage.known"),
            unknown_reason=_optional_text(
                mapping["unknown_reason"], "usage.unknown_reason"
            ),
        )


def _optional_token_count(value: object, field: str) -> int | None:
    return None if value is None else _integer(value, field, minimum=0)


@dataclass(frozen=True)
class CostObservation:
    amount_usd: Decimal | None
    complete: bool
    pricing_version: str | None
    unknown_reason: str | None

    def __post_init__(self) -> None:
        complete = _boolean(self.complete, "cost.complete")
        pricing_version = _optional_text(self.pricing_version, "pricing_version")
        reason = _optional_text(self.unknown_reason, "cost.unknown_reason")
        if self.amount_usd is not None:
            _decimal(self.amount_usd, "amount_usd")
        if complete:
            if self.amount_usd is None or pricing_version is None or reason is not None:
                raise ContractViolation(
                    "complete cost requires an amount and pricing version without "
                    "unknown reason"
                )
        elif self.amount_usd is not None or reason is None:
            raise ContractViolation(
                "incomplete cost requires a null amount and an unknown reason"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CostObservation":
        mapping = _as_mapping(value, "cost observation")
        _check_fields(
            mapping,
            "cost observation",
            {"amount_usd", "complete", "pricing_version", "unknown_reason"},
        )
        amount = mapping["amount_usd"]
        return cls(
            amount_usd=_decimal(amount, "amount_usd") if amount is not None else None,
            complete=_boolean(mapping["complete"], "cost.complete"),
            pricing_version=_optional_text(
                mapping["pricing_version"], "pricing_version"
            ),
            unknown_reason=_optional_text(
                mapping["unknown_reason"], "cost.unknown_reason"
            ),
        )


@dataclass(frozen=True)
class StageUsageEvent:
    schema_version: SchemaVersion
    timestamp: datetime
    event_id: str
    case_id: str
    analysis_id: str
    analysis_revision: int
    stage: Stage
    attempt: int
    run_mode: RunMode
    input_size_bucket: InputSizeBucket
    requested_model: str
    served_model: str | None
    prompt_version: str
    stage_schema_version: str
    policy_version: str
    model_policy_version: str
    succeeded: bool
    error_category: str | None
    duration_ms: int
    usage: TokenUsage
    cost: CostObservation

    def __post_init__(self) -> None:
        _schema_version(self.schema_version)
        _utc_timestamp(self.timestamp, "timestamp")
        for field in ("event_id", "case_id", "analysis_id"):
            _text(getattr(self, field), field)
        _integer(self.analysis_revision, "analysis_revision", minimum=1)
        _require_enum(Stage, self.stage, "stage")
        _integer(self.attempt, "attempt", minimum=1)
        _require_enum(RunMode, self.run_mode, "run_mode")
        _require_enum(InputSizeBucket, self.input_size_bucket, "input_size_bucket")
        _text(self.requested_model, "requested_model")
        _optional_text(self.served_model, "served_model")
        _text(self.prompt_version, "prompt_version")
        _text(self.stage_schema_version, "stage_schema_version")
        _text(self.policy_version, "policy_version")
        _text(self.model_policy_version, "model_policy_version")
        succeeded = _boolean(self.succeeded, "succeeded")
        error_category = _optional_text(self.error_category, "error_category")
        if succeeded and error_category is not None:
            raise ContractViolation(
                "successful usage event cannot have an error category"
            )
        if not succeeded and error_category is None:
            raise ContractViolation("failed usage event requires an error category")
        _integer(self.duration_ms, "duration_ms", minimum=0)
        if not isinstance(self.usage, TokenUsage) or not isinstance(
            self.cost, CostObservation
        ):
            raise ContractViolation("usage event requires typed usage and cost records")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "StageUsageEvent":
        mapping = _as_mapping(value, "stage usage event")
        _check_fields(
            mapping,
            "stage usage event",
            {
                "schema_version",
                "timestamp",
                "event_id",
                "case_id",
                "analysis_id",
                "analysis_revision",
                "stage",
                "attempt",
                "run_mode",
                "input_size_bucket",
                "requested_model",
                "served_model",
                "prompt_version",
                "stage_schema_version",
                "policy_version",
                "model_policy_version",
                "succeeded",
                "error_category",
                "duration_ms",
                "usage",
                "cost",
            },
        )
        return cls(
            schema_version=_schema_version(mapping["schema_version"]),
            timestamp=_parse_utc_timestamp(mapping["timestamp"], "timestamp"),
            event_id=_text(mapping["event_id"], "event_id"),
            case_id=_text(mapping["case_id"], "case_id"),
            analysis_id=_text(mapping["analysis_id"], "analysis_id"),
            analysis_revision=_integer(
                mapping["analysis_revision"], "analysis_revision", minimum=1
            ),
            stage=_enum(Stage, mapping["stage"], "stage"),
            attempt=_integer(mapping["attempt"], "attempt", minimum=1),
            run_mode=_enum(RunMode, mapping["run_mode"], "run_mode"),
            input_size_bucket=_enum(
                InputSizeBucket, mapping["input_size_bucket"], "input_size_bucket"
            ),
            requested_model=_text(mapping["requested_model"], "requested_model"),
            served_model=_optional_text(mapping["served_model"], "served_model"),
            prompt_version=_text(mapping["prompt_version"], "prompt_version"),
            stage_schema_version=_text(
                mapping["stage_schema_version"], "stage_schema_version"
            ),
            policy_version=_text(mapping["policy_version"], "policy_version"),
            model_policy_version=_text(
                mapping["model_policy_version"], "model_policy_version"
            ),
            succeeded=_boolean(mapping["succeeded"], "succeeded"),
            error_category=_optional_text(mapping["error_category"], "error_category"),
            duration_ms=_integer(mapping["duration_ms"], "duration_ms", minimum=0),
            usage=TokenUsage.from_mapping(_as_mapping(mapping["usage"], "token usage")),
            cost=CostObservation.from_mapping(
                _as_mapping(mapping["cost"], "cost observation")
            ),
        )


@dataclass(frozen=True)
class ModelDecision:
    stage: Stage
    model: str
    policy_version: str
    reason: str

    def __post_init__(self) -> None:
        _require_enum(Stage, self.stage, "stage")
        _text(self.model, "model")
        _text(self.policy_version, "policy_version")
        _text(self.reason, "reason", maximum=MAX_POLICY_REASON_LENGTH)


class ModelPolicy(Protocol):
    def resolve(
        self, stage: Stage, approved_config: Mapping[str, object]
    ) -> ModelDecision: ...


class OnlineEvaluator(Protocol):
    def check(
        self, result: AnalysisResult, policy_context: Mapping[str, object]
    ) -> EvaluationResult: ...


class FeedbackMerger(Protocol):
    def merge(
        self,
        existing_candidate: AnnotationCandidate | None,
        signal: SignalReference,
    ) -> AnnotationCandidate: ...
