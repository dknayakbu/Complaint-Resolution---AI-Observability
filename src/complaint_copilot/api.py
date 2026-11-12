"""Fixture-first FastAPI surface for complaint demonstrations."""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)
from pydantic import BaseModel, Field, field_validator

from complaint_copilot.baseline import BASELINE_PROMPT_VERSION, SingleCallBaseline
from complaint_copilot.contracts import (
    AdjudicatedLabel,
    AnalysisRequest,
    AnnotationCandidate,
    AnnotationStatus,
    Category,
    FeedbackInput,
    FeedbackRating,
    IncidentPriority,
    QueueKey,
    RunMode,
    Severity,
    SignalReference,
    Stage,
)
from complaint_copilot.demo_replay import (
    measure_batch_drift,
    measure_embedding_drift,
    replay_cost,
    replay_drift,
    replay_embedding_drift,
    replay_quality,
    replay_slo,
)
from complaint_copilot.embedding_drift import EmbeddingUnavailableError
from complaint_copilot.feedback import merge
from complaint_copilot.instrumentation import flush_telemetry, instruments, tracer
from complaint_copilot.model_policy import StageModelPolicy
from complaint_copilot.orchestrator import ComplaintOrchestrator
from complaint_copilot.provider import (
    FixtureProvider,
    OpenAIProvider,
    Provider,
    ProviderFailure,
    RetryingProvider,
)
from complaint_copilot.repository import (
    ConcurrentUpdate,
    IdempotencyConflict,
    InvalidCaseState,
    RecordNotFound,
    RepositoryError,
    SQLiteRepository,
)
from complaint_copilot.settings import AppSettings
from complaint_copilot.slo import compute_sli, error_budget_remaining

_bearer = HTTPBearer(auto_error=False)
_internal_basic = HTTPBasic(auto_error=False)


class IntakeBody(BaseModel):
    complaint_text: str = Field(min_length=1, max_length=20_000)
    synthetic: bool = True
    source_sample_id: str | None = Field(default=None, max_length=200)

    @field_validator("complaint_text")
    @classmethod
    def complaint_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("complaint_text must not be blank")
        return value

    @field_validator("synthetic")
    @classmethod
    def require_synthetic(cls, value: bool) -> bool:
        if not value:
            raise ValueError("only invented complaints are accepted")
        return value


class ReviewBody(BaseModel):
    expected_case_version: int = Field(ge=1)
    analysis_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    category: Category
    queue: QueueKey

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("review reason must not be blank")
        return value


class FeedbackBody(BaseModel):
    analysis_revision: int = Field(ge=1)
    rating: FeedbackRating
    note: str | None = Field(default=None, max_length=2000)


class AdjudicationBody(BaseModel):
    expected_case_version: int = Field(ge=1)
    analysis_revision: int = Field(ge=1)
    case_id: str = Field(min_length=1, max_length=200)
    category: Category
    severity: Severity
    queue: QueueKey
    draft_rubric_assessment: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)


class BatchDriftBody(BaseModel):
    case_ids: list[str] = Field(min_length=10)

    @field_validator("case_ids")
    @classmethod
    def unique_case_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("case IDs must be unique")
        return value


def create_app(
    settings: AppSettings | None = None,
    *,
    repository: SQLiteRepository | None = None,
    provider: Provider | None = None,
) -> FastAPI:
    config = settings or AppSettings.from_env()
    repo = repository or SQLiteRepository(config.database_path)
    active_provider = provider or _provider_for(config)
    if provider is None:
        active_provider = RetryingProvider(
            active_provider, max_attempts=config.max_provider_attempts
        )
    policy = StageModelPolicy(
        approved_mapping={
            Stage.CLASSIFICATION: config.classification_model or config.model,
            Stage.DRAFTING: config.drafting_model or config.model,
            Stage.EVALUATION: config.evaluation_model or config.model,
        }
    )
    workflow = ComplaintOrchestrator(
        repository=repo,
        provider=active_provider,
        policy=policy,
        model_policy_version=policy.policy_version,
        run_mode=RunMode.FIXTURE if config.mode == "fixture" else RunMode.DEMO,
        short_input_max=(
            config.short_input_max if config.short_input_max is not None else 2_000
        ),
        medium_input_max=(
            config.medium_input_max if config.medium_input_max is not None else 8_000
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        repo.recover_interrupted(datetime.now(UTC))
        yield

    app = FastAPI(
        title="Complaint Resolution Co-Pilot Demo",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.repository = repo
    app.state.provider = active_provider
    app.state.workflow = workflow
    app.state.data_root = Path(
        os.getenv("DEMO_DATA_PATH", str(Path(__file__).resolve().parents[2] / "data"))
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/mode")
    def mode() -> dict[str, str]:
        return {
            "mode": config.mode,
            "provider": "fixture" if config.mode == "fixture" else "openai",
            "warning": (
                "Scripted fixture responses; not model behavior."
                if config.mode == "fixture"
                else "Live OpenAI provider; calls may incur cost."
            ),
        }

    @app.get("/api/model-policy")
    def model_policy() -> dict[str, object]:
        assignments = {
            stage.value: policy.resolve(stage, {}).model
            for stage in (Stage.CLASSIFICATION, Stage.DRAFTING, Stage.EVALUATION)
        }
        return {
            "policy_version": policy.policy_version,
            "mode": config.mode,
            "stage_models": assignments,
            "routing_basis": "stage_only",
            "severity_based_routing": False,
        }

    @app.get("/api/operations/slo")
    def operations_slo() -> dict[str, object]:
        window_size = 30
        run_mode = RunMode.FIXTURE if config.mode == "fixture" else RunMode.DEMO
        events = repo.list_recent_completion_events(window_size, run_mode.value)
        outcomes = [str(event.get("analysis_outcome", "")) for event in events]
        good = sum(outcome == "complete" for outcome in outcomes)
        bad = sum(outcome == "manual_required" for outcome in outcomes)
        unknown = len(outcomes) - good - bad
        eligible = good + bad
        sli = compute_sli(
            good=good,
            bad=bad,
            unknown=unknown,
            eligible_samples=eligible,
        )
        return {
            "status": "measured" if eligible == window_size else "insufficient_sample",
            "target": "0.99",
            "window_size": window_size,
            "eligible_samples": eligible,
            "good": good,
            "bad": bad,
            "unknown": unknown,
            "good_rate": str(sli.good_rate),
            "bad_rate": str(sli.bad_rate),
            "error_budget_remaining": str(
                error_budget_remaining(
                    target_slo=Decimal("0.99"),
                    total_samples=eligible,
                    bad_samples=bad,
                )
            ),
        }

    @app.post("/api/cases", status_code=status.HTTP_201_CREATED)
    def intake(
        body: IntakeBody,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
    ) -> dict[str, object]:
        if config.mode == "live" and body.source_sample_id is not None:
            raise HTTPException(
                status_code=422,
                detail="source_sample_id fixture controls are unavailable in live mode",
            )
        try:
            return workflow.process(
                complaint_text=body.complaint_text,
                idempotency_key=idempotency_key,
                source_sample_id=body.source_sample_id,
            )
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, RepositoryError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/cases")
    def list_cases() -> list[dict[str, object]]:
        return repo.list_cases()

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, object]:
        try:
            return repo.get_case(case_id)
        except RecordNotFound as error:
            raise HTTPException(status_code=404, detail="case not found") from error

    @app.get("/api/queue")
    def queue() -> list[dict[str, object]]:
        return repo.list_queue()

    @app.post("/api/cases/{case_id}/review")
    def review(
        case_id: str,
        body: ReviewBody,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> dict[str, object]:
        reviewer = _authorized_actor(credentials, config.reviewer_token)
        try:
            case = repo.get_case(case_id)
            current = _current_analysis(case, body.analysis_revision)
            result = _mapping(current.get("result"))
            classification = _mapping(result.get("classification"))
            original_category = Category(str(classification["category"]))
            effective_raw = result.get("effective_severity")
            model_severity_raw = classification.get("model_severity")
            if type(effective_raw) is not int or type(model_severity_raw) is not int:
                raise HTTPException(
                    status_code=409, detail="classification record is incomplete"
                )
            effective_severity = Severity(effective_raw)
            if (
                body.category is not original_category
                or body.queue.value != original_category.value
            ):
                raise HTTPException(
                    status_code=409,
                    detail="classification corrections require a new analysis revision",
                )
            acknowledgement = result.get("draft")
            if not isinstance(acknowledgement, str) or not acknowledgement:
                raise HTTPException(
                    status_code=409, detail="analysis has no approvable draft"
                )
            with tracer.start_as_current_span(
                "review.approval",
                attributes={
                    "review.role": "reviewer",
                    "review.action": "approve_and_route",
                    "run.mode": config.mode,
                },
            ):
                routed = repo.apply_review(
                    review_id=secrets.token_urlsafe(18),
                    case_id=case_id,
                    analysis_revision=body.analysis_revision,
                    expected_case_version=body.expected_case_version,
                    reviewer=reviewer,
                    reason=body.reason.strip(),
                    category=original_category.value,
                    model_severity=model_severity_raw,
                    effective_severity=int(effective_severity),
                    queue=body.queue.value,
                    acknowledgement=acknowledgement,
                    now=datetime.now(UTC),
                )
            instruments.review_backlog.add(-1, {"run_mode": config.mode})
            instruments.reviews.add(
                1, {"run_mode": config.mode, "outcome": "approved_routed"}
            )
            flush_telemetry()
            return routed
        except HTTPException:
            raise
        except RecordNotFound as error:
            raise HTTPException(status_code=404, detail="case not found") from error
        except (ConcurrentUpdate, InvalidCaseState) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/cases/{case_id}/feedback")
    def feedback(
        case_id: str,
        body: FeedbackBody,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> dict[str, object]:
        actor = _authorized_actor(credentials, config.reviewer_token)
        feedback_input = FeedbackInput(
            case_id=case_id,
            analysis_revision=body.analysis_revision,
            rating=body.rating,
            note=body.note,
        )
        try:
            saved = repo.save_feedback(
                feedback_input,
                feedback_id=secrets.token_urlsafe(18),
                actor=actor,
                source="review_ui",
                now=datetime.now(UTC),
            )
            if body.rating is not FeedbackRating.DOWN:
                return saved
            signal = SignalReference(
                source="human_feedback",
                reference_id=f"{case_id}:rev{body.analysis_revision}",
                reason_code="human_quality_feedback",
            )
            candidate = merge(
                _pending_candidate(
                    repo.list_annotations(), case_id, body.analysis_revision
                ),
                signal,
            )
            saved["annotation_id"] = repo.merge_annotation_candidate(
                candidate, datetime.now(UTC)
            )
            return saved
        except RecordNotFound as error:
            raise HTTPException(
                status_code=404, detail="case or revision not found"
            ) from error

    @app.post("/api/baseline")
    def baseline(body: IntakeBody) -> dict[str, object]:
        if config.mode == "live" and body.source_sample_id is not None:
            raise HTTPException(
                status_code=422,
                detail="source_sample_id fixture controls are unavailable in live mode",
            )
        request = AnalysisRequest(
            complaint_text=body.complaint_text,
            synthetic=True,
            source_sample_id=body.source_sample_id,
        )
        decision = policy.resolve(Stage.CLASSIFICATION, {})
        model = decision.model
        baseline_provider = active_provider
        try:
            result = SingleCallBaseline(baseline_provider, model).run(request)
        except (ProviderFailure, ValueError, TypeError) as error:
            raise HTTPException(
                status_code=502, detail="baseline provider or output validation failed"
            ) from error
        return {
            "mode": config.mode,
            "baseline_prompt_version": BASELINE_PROMPT_VERSION,
            "result": result.as_mapping(),
        }

    @app.post("/internal/alerts")
    def alert_webhook(
        payload: dict[str, object],
        internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
        basic_credentials: Annotated[
            HTTPBasicCredentials | None, Depends(_internal_basic)
        ] = None,
    ) -> dict[str, object]:
        _require_alert_internal(
            internal_token, basic_credentials, config.internal_token
        )
        alert_rows = payload.get("alerts")
        alerts = (
            [row for row in alert_rows if isinstance(row, Mapping)]
            if isinstance(alert_rows, list)
            else []
        )
        first_alert = alerts[0] if alerts else {}
        common_labels = payload.get("commonLabels")
        labels = common_labels if isinstance(common_labels, Mapping) else {}
        fingerprint_value = payload.get("fingerprint") or payload.get("id")
        if fingerprint_value is None:
            fingerprints = sorted(
                str(alert["fingerprint"])
                for alert in alerts
                if alert.get("fingerprint")
            )
            fingerprint_value = "|".join(fingerprints)
        fingerprint = str(fingerprint_value or "")
        if len(fingerprint) > 200:
            fingerprint = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        episode_value = first_alert.get("startsAt")
        episode_id = str(episode_value) if episode_value is not None else ""
        if len(episode_id) > 100:
            episode_id = hashlib.sha256(episode_id.encode("utf-8")).hexdigest()
        status_value = str(payload.get("status") or payload.get("state") or "firing")
        if status_value.lower() in {"resolved", "ok", "normal"}:
            normalized_status = "resolved"
        elif status_value.lower() in {"firing", "active", "alerting"}:
            normalized_status = "firing"
        else:
            normalized_status = ""
        alert_labels = first_alert.get("labels", {})
        if not isinstance(alert_labels, Mapping):
            alert_labels = {}
        priority_candidate = str(
            payload.get("priority")
            or labels.get("incident_priority")
            or alert_labels.get("incident_priority")
            or "P3"
        ).upper()
        priority = (
            priority_candidate
            if priority_candidate in {item.value for item in IncidentPriority}
            else IncidentPriority.P3.value
        )
        name = str(
            payload.get("title")
            or payload.get("name")
            or labels.get("alertname")
            or alert_labels.get("alertname")
            or "Alert"
        )
        if not fingerprint.strip():
            raise HTTPException(status_code=422, detail="alert fingerprint is required")
        if not normalized_status:
            raise HTTPException(
                status_code=422, detail="alert status must be firing or resolved"
            )
        event_id = (
            f"{fingerprint}:{episode_id}:{normalized_status}"
            if episode_id
            else f"{fingerprint}:{normalized_status}"
        )
        stored = repo.store_alert(
            event_id=event_id,
            received_at=datetime.now(UTC),
            status=normalized_status,
            priority=priority,
            name=name,
            payload={
                "status": normalized_status,
                "priority": priority,
                "name": name,
            },
        )
        if stored:
            instruments.incident_events.add(
                1,
                {"status": normalized_status, "priority": priority.upper()},
            )
            flush_telemetry()
        return {"accepted": True, "duplicate": not stored}

    @app.post("/internal/demo/batch-drift")
    def batch_drift(
        body: BatchDriftBody,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
        internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> dict[str, object]:
        _require_internal(internal_token, config.internal_token)
        try:
            complaints = [
                {"complaint_text": repo.get_case(case_id)["complaint_text"]}
                for case_id in body.case_ids
            ]
            result = measure_batch_drift(app.state.data_root, complaints)
            digest = hashlib.sha256(
                "\n".join(sorted(body.case_ids)).encode("utf-8")
            ).hexdigest()
            stored_result, created = repo.store_demo_replay(
                idempotency_key=idempotency_key,
                scenario=f"batch-drift:{digest}",
                result=result,
                now=datetime.now(UTC),
            )
        except RecordNotFound as error:
            raise HTTPException(status_code=404, detail="case not found") from error
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if created:
            run_mode = RunMode.DEMO if config.mode == "live" else RunMode.FIXTURE
            instruments.drift_scores.record(
                float(result["score_base2_jsd"]),
                {"run_mode": run_mode.value, "replay": "batch"},
            )
            flush_telemetry()
        return {**stored_result, "duplicate": not created}

    @app.post("/internal/demo/batch-embedding-drift")
    def batch_embedding_drift(
        body: BatchDriftBody,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
        internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> dict[str, object]:
        _require_internal(internal_token, config.internal_token)
        try:
            complaints = [
                {"complaint_text": repo.get_case(case_id)["complaint_text"]}
                for case_id in body.case_ids
            ]
            result = measure_embedding_drift(app.state.data_root, [complaints])
            digest = hashlib.sha256(
                "\n".join(sorted(body.case_ids)).encode("utf-8")
            ).hexdigest()
            stored_result, created = repo.store_demo_replay(
                idempotency_key=idempotency_key,
                scenario=f"batch-embedding-drift:{digest}",
                result=result,
                now=datetime.now(UTC),
            )
        except RecordNotFound as error:
            raise HTTPException(status_code=404, detail="case not found") from error
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except EmbeddingUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if created:
            run_mode = RunMode.DEMO if config.mode == "live" else RunMode.FIXTURE
            _record_replay_metrics("embedding_batch", result, run_mode=run_mode)
            flush_telemetry()
        return {**stored_result, "duplicate": not created}

    @app.post("/internal/demo/replay/{scenario}")
    def replay(
        scenario: str,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
        internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> dict[str, object]:
        _require_internal(internal_token, config.internal_token)
        try:
            if scenario == "drift":
                output = replay_drift(app.state.data_root)
            elif scenario == "embedding":
                output = replay_embedding_drift(app.state.data_root)
            elif scenario == "cost":
                output = replay_cost()
            elif scenario == "quality":
                output = replay_quality(app.state.data_root)
            elif scenario == "slo":
                output = replay_slo()
            else:
                raise HTTPException(status_code=404, detail="unknown replay scenario")
            stored_result, created = repo.store_demo_replay(
                idempotency_key=idempotency_key,
                scenario=scenario,
                result=output,
                now=datetime.now(UTC),
            )
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except EmbeddingUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if created:
            run_mode = RunMode.DEMO if config.mode == "live" else RunMode.FIXTURE
            _record_replay_metrics(scenario, output, run_mode=run_mode)
            flush_telemetry()
        return {**stored_result, "duplicate": not created}

    @app.get("/api/alerts")
    def list_alerts() -> list[dict[str, object]]:
        return repo.list_alerts()

    @app.post("/api/annotations/{annotation_id}/adjudicate")
    def adjudicate(
        annotation_id: str,
        body: AdjudicationBody,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> dict[str, object]:
        reviewer = _authorized_actor(credentials, config.reviewer_token)
        try:
            return repo.adjudicate_label(
                label_id=secrets.token_urlsafe(18),
                annotation_id=annotation_id,
                label=AdjudicatedLabel(
                    case_id=body.case_id,
                    analysis_revision=body.analysis_revision,
                    category=body.category,
                    severity=body.severity,
                    queue=body.queue,
                    draft_rubric_assessment=body.draft_rubric_assessment,
                    reviewer=reviewer,
                    reason=body.reason,
                    label_version="demo-label-v1",
                ),
                expected_case_version=body.expected_case_version,
                now=datetime.now(UTC),
            )
        except RecordNotFound as error:
            raise HTTPException(
                status_code=404, detail="case or annotation was not found"
            ) from error
        except (ConcurrentUpdate, InvalidCaseState) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/annotations")
    def list_annotations() -> list[dict[str, object]]:
        return repo.list_annotations()

    return app


def _require_internal(value: str | None, expected: str) -> None:
    if not value or not secrets.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="internal authorization required")


def _require_alert_internal(
    token: str | None, credentials: HTTPBasicCredentials | None, expected: str
) -> None:
    if token and secrets.compare_digest(token, expected):
        return
    if (
        credentials is not None
        and credentials.username == "grafana-alerting"
        and secrets.compare_digest(credentials.password, expected)
    ):
        return
    raise HTTPException(status_code=401, detail="internal authorization required")


def _pending_candidate(
    rows: list[dict[str, object]], case_id: str, revision: int
) -> AnnotationCandidate | None:
    for row in rows:
        candidate_value = row.get("candidate")
        if not isinstance(candidate_value, Mapping):
            continue
        if (
            candidate_value.get("case_id") != case_id
            or candidate_value.get("analysis_revision") != revision
            or row.get("status") != AnnotationStatus.PENDING.value
        ):
            continue
        raw_signals = candidate_value.get("signals")
        raw_links = candidate_value.get("evidence_links")
        if not isinstance(raw_signals, list) or not isinstance(raw_links, list):
            continue
        signals = tuple(
            SignalReference(
                source=str(signal["source"]),
                reference_id=str(signal["reference_id"]),
                reason_code=str(signal["reason_code"]),
            )
            for signal in raw_signals
            if isinstance(signal, Mapping)
        )
        return AnnotationCandidate(
            case_id=case_id,
            analysis_revision=revision,
            signals=signals,
            priority=str(candidate_value["priority"]),
            evidence_links=tuple(str(link) for link in raw_links),
            status=AnnotationStatus.PENDING,
        )
    return None


def _record_replay_metrics(
    scenario: str, result: Mapping[str, object], *, run_mode: RunMode
) -> None:
    labels = {"run_mode": run_mode.value, "replay": scenario}
    if scenario == "drift":
        scores = result.get("window_scores_base2_jsd")
        if isinstance(scores, list):
            for index, value in enumerate(scores, start=1):
                if isinstance(value, (int, float)):
                    instruments.drift_scores.record(
                        float(value), {**labels, "window": str(index)}
                    )
        if result.get("warning_after_consecutive_windows") is True:
            instruments.drift_warnings.add(1, labels)
    elif scenario in {"embedding", "embedding_batch"}:
        scores = result.get("cosine_distances")
        if isinstance(scores, list):
            for index, value in enumerate(scores, start=1):
                if isinstance(value, (int, float)):
                    instruments.embedding_drift.set(
                        float(value), {**labels, "window": str(index)}
                    )
    elif scenario == "cost":
        ratios = result.get("ratios_initial_then_each_observation")
        if isinstance(ratios, list):
            for value in ratios:
                try:
                    instruments.cost_ratios.record(float(str(value)), labels)
                except ValueError:
                    continue
        if result.get("threshold_crossing_spike_observation") is not None:
            instruments.cost_anomalies.add(1, labels)
    elif scenario == "quality":
        for pack_name in ("q0", "q1"):
            pack = result.get(pack_name)
            if not isinstance(pack, Mapping):
                continue
            for field, metric_type in (
                ("raw_sev1_recall", "raw"),
                ("effective_sev1_recall", "effective"),
            ):
                value = pack.get(field)
                if isinstance(value, (int, float)):
                    instruments.quality_recall.record(
                        float(value),
                        {
                            **labels,
                            "pack": pack_name.upper(),
                            "metric_type": metric_type,
                        },
                    )
    elif scenario == "slo":
        for phase in ("healthy", "one_terminal_failure", "after_30_fresh_successes"):
            snapshot = result.get(phase)
            if isinstance(snapshot, Mapping):
                for outcome in ("good", "bad"):
                    count = snapshot.get(outcome)
                    if isinstance(count, int) and count > 0:
                        instruments.slo_outcomes.add(
                            count,
                            {**labels, "phase": phase, "outcome": outcome},
                        )


def _provider_for(settings: AppSettings) -> Provider:
    if settings.mode == "fixture":
        return FixtureProvider()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for live provider mode")
    return OpenAIProvider(
        settings.openai_api_key,
        settings.request_timeout_seconds,
    )


def _authorized_actor(
    credentials: HTTPAuthorizationCredentials | None, expected_token: str
) -> str:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected_token)
    ):
        raise HTTPException(status_code=403, detail="reviewer permission required")
    return "demo-reviewer"


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HTTPException(status_code=409, detail="analysis record is unavailable")
    return value


def _current_analysis(
    case: Mapping[str, object], revision: int
) -> Mapping[str, object]:
    analyses = case.get("analyses")
    if not isinstance(analyses, list):
        raise HTTPException(status_code=409, detail="analysis record is unavailable")
    for analysis in analyses:
        if isinstance(analysis, Mapping) and analysis.get("revision") == revision:
            return analysis
    raise HTTPException(status_code=409, detail="analysis revision is not available")


app = create_app()
