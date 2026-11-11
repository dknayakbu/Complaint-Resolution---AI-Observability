"""Sequential complaint workflow using the shared records and phase adapters."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from opentelemetry.trace import Span

from complaint_copilot.acknowledgement import (
    DRAFTING_PROMPT_VERSION,
    DRAFTING_SCHEMA_VERSION,
    AcknowledgementDraftingAgent,
    assemble_acknowledgement,
)
from complaint_copilot.classification import (
    CLASSIFICATION_PROMPT_VERSION,
    CLASSIFICATION_SCHEMA_VERSION,
    ClassificationAgent,
)
from complaint_copilot.contracts import (
    AnalysisCompletionEvent,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisResult,
    CaseState,
    ContractViolation,
    CostObservation,
    CostSummary,
    FailureCode,
    InputSizeBucket,
    ModelPolicy,
    RunMode,
    Severity,
    SignalReference,
    Stage,
    StageOutcomeRecord,
    StageStatus,
    StageUsageEvent,
    TokenUsage,
)
from complaint_copilot.cost import CostError, calculate_usage_cost
from complaint_copilot.feedback import merge
from complaint_copilot.instrumentation import flush_telemetry, instruments, tracer
from complaint_copilot.policy import (
    apply_safeguards,
    queue_for_category,
    validate_classification,
    validate_draft,
)
from complaint_copilot.provider import Provider, ProviderFailure, ProviderResponse
from complaint_copilot.repository import SQLiteRepository

Clock = Callable[[], datetime]


def _failure_code(error: ProviderFailure) -> FailureCode:
    if error.code == "provider_timeout":
        return FailureCode.PROVIDER_TIMEOUT
    return FailureCode.PROVIDER_ERROR


def _input_bucket(text: str, *, short_max: int, medium_max: int) -> InputSizeBucket:
    if len(text) <= short_max:
        return InputSizeBucket.SHORT
    if len(text) <= medium_max:
        return InputSizeBucket.MEDIUM
    return InputSizeBucket.LONG


class ComplaintOrchestrator:
    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        provider: Provider,
        policy: ModelPolicy,
        model_policy_version: str,
        run_mode: RunMode,
        short_input_max: int = 2_000,
        medium_input_max: int = 8_000,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        if short_input_max <= 0 or medium_input_max <= short_input_max:
            raise ValueError("input bucket limits must be positive and ordered")
        self._repository = repository
        self._provider = provider
        self._policy = policy
        self._model_policy_version = model_policy_version
        self._run_mode = run_mode
        self._short_input_max = short_input_max
        self._medium_input_max = medium_input_max
        self._clock = clock
        self._classification_agent = ClassificationAgent(
            provider,
            include_fixture_metadata=run_mode is RunMode.FIXTURE,
        )
        self._drafting_agent = AcknowledgementDraftingAgent(provider)

    def process(
        self,
        *,
        complaint_text: str,
        idempotency_key: str,
        source_sample_id: str | None = None,
    ) -> dict[str, object]:
        request = AnalysisRequest(
            complaint_text=complaint_text,
            synthetic=True,
            source_sample_id=source_sample_id,
        )
        case_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        case_id, created = self._repository.create_intake(
            case_id=case_id,
            request_id=request_id,
            complaint_text=request.complaint_text,
            source_sample_id=request.source_sample_id,
            idempotency_key=idempotency_key,
            now=self._clock(),
        )
        if created:
            self._process_case(case_id, request_id, request)
        return self._repository.get_case(case_id)

    def _process_case(
        self, case_id: str, request_id: str, request: AnalysisRequest
    ) -> None:
        with tracer.start_as_current_span("complaint.analysis") as span:
            span.set_attribute("run.mode", self._run_mode.value)
            span.set_attribute("complaint.synthetic", True)
            trace_context = span.get_span_context()
            trace_id = (
                f"{trace_context.trace_id:032x}"
                if trace_context.is_valid
                else uuid.uuid4().hex
            )
            instruments.requests.add(1, {"run_mode": self._run_mode.value})
            self._run_case(
                case_id=case_id,
                request_id=request_id,
                request=request,
                trace_id=trace_id,
            )
            case = self._repository.get_case(case_id)
            span.set_attribute("analysis.outcome", str(case["state"]))
            if case["state"] == CaseState.AWAITING_REVIEW.value:
                instruments.review_backlog.add(1, {"run_mode": self._run_mode.value})
            flush_telemetry()

    def _run_case(
        self,
        *,
        case_id: str,
        request_id: str,
        request: AnalysisRequest,
        trace_id: str,
    ) -> None:
        started = time.monotonic()
        analysis_id = str(uuid.uuid4())
        case = self._repository.get_case(case_id)
        revision = self._repository.begin_analysis(
            case_id=case_id,
            expected_version=int(cast(int, case["version"])),
            analysis_id=analysis_id,
            trace_id=trace_id,
            now=self._clock(),
        )
        classification_decision = self._policy.resolve(Stage.CLASSIFICATION, {})
        stage_events: list[StageUsageEvent] = []
        classification = None
        effective_severity: Severity | None = None
        policy_flags: tuple[str, ...] = ()
        draft: str | None = None
        classification_status = StageStatus.FAILED
        drafting_status = StageStatus.SKIPPED
        classification_failure: FailureCode | None = None
        drafting_failure: FailureCode | None = None
        classification_response: ProviderResponse | None = None
        drafting_response: ProviderResponse | None = None
        classification_attempts = 1
        drafting_attempts = 1
        classification_duration = 0
        drafting_duration = 0

        classification_started = time.monotonic()
        try:
            with tracer.start_as_current_span(
                "agent.classification",
                attributes={
                    "agent.stage": Stage.CLASSIFICATION.value,
                    "gen_ai.request.model": classification_decision.model,
                    "model.requested": classification_decision.model,
                    "run.mode": self._run_mode.value,
                },
            ) as span:
                classification_response = self._classification_agent.run(
                    request, classification_decision
                )
                classification_attempts = classification_response.attempts
                _record_generation_attributes(span, classification_response)
            classification = validate_classification(
                classification_response.content, request.complaint_text
            )
            effective_severity, policy_flags = apply_safeguards(
                request.complaint_text, classification
            )
            classification_status = StageStatus.SUCCEEDED
            self._repository.save_classification(
                case_id=case_id,
                revision=revision,
                classification=classification,
                effective_severity=int(effective_severity),
                proposed_queue=queue_for_category(classification.category).value,
                policy_flags=policy_flags,
                now=self._clock(),
            )
        except ProviderFailure as error:
            classification_failure = _failure_code(error)
            classification_attempts = error.attempts
            classification_response = error.usage
        except (ContractViolation, ValueError, json.JSONDecodeError):
            classification_failure = FailureCode.CLASSIFICATION_INVALID
        finally:
            classification_duration = int(
                (time.monotonic() - classification_started) * 1000
            )
            stage_events.append(
                self._stage_event(
                    case_id=case_id,
                    analysis_id=analysis_id,
                    revision=revision,
                    stage=Stage.CLASSIFICATION,
                    model=classification_decision.model,
                    complaint_text=request.complaint_text,
                    prompt_version=CLASSIFICATION_PROMPT_VERSION,
                    schema_version=CLASSIFICATION_SCHEMA_VERSION,
                    duration_ms=classification_duration,
                    succeeded=classification_status is StageStatus.SUCCEEDED,
                    failure=classification_failure,
                    response=classification_response,
                    attempt=classification_attempts,
                )
            )

        if classification is not None and effective_severity is not None:
            drafting_decision = self._policy.resolve(Stage.DRAFTING, {})
            drafting_status = StageStatus.FAILED
            drafting_started = time.monotonic()
            try:
                with tracer.start_as_current_span(
                    "agent.drafting",
                    attributes={
                        "agent.stage": Stage.DRAFTING.value,
                        "gen_ai.request.model": drafting_decision.model,
                        "model.requested": drafting_decision.model,
                        "run.mode": self._run_mode.value,
                    },
                ) as span:
                    drafting_response = self._drafting_agent.run(
                        request, classification, effective_severity, drafting_decision
                    )
                    drafting_attempts = drafting_response.attempts
                    _record_generation_attributes(span, drafting_response)
                personalized = validate_draft(drafting_response.content)
                draft = assemble_acknowledgement(personalized)
                drafting_status = StageStatus.SUCCEEDED
            except ProviderFailure as error:
                drafting_failure = _failure_code(error)
                drafting_attempts = error.attempts
                drafting_response = error.usage
            except (ContractViolation, ValueError, json.JSONDecodeError):
                drafting_failure = FailureCode.DRAFTING_INVALID
            finally:
                drafting_duration = int((time.monotonic() - drafting_started) * 1000)
                stage_events.append(
                    self._stage_event(
                        case_id=case_id,
                        analysis_id=analysis_id,
                        revision=revision,
                        stage=Stage.DRAFTING,
                        model=drafting_decision.model,
                        complaint_text=request.complaint_text,
                        prompt_version=DRAFTING_PROMPT_VERSION,
                        schema_version=DRAFTING_SCHEMA_VERSION,
                        duration_ms=drafting_duration,
                        succeeded=drafting_status is StageStatus.SUCCEEDED,
                        failure=drafting_failure,
                        response=drafting_response,
                        attempt=drafting_attempts,
                    )
                )

        for event in stage_events:
            self._repository.record_stage_event(event)
            _record_stage_metrics(event)
        if policy_flags:
            instruments.safety_promotions.add(
                1,
                {
                    "run_mode": self._run_mode.value,
                    "policy_flag": "covered_safety_signal",
                },
            )

        complete = (
            classification_status is StageStatus.SUCCEEDED
            and drafting_status is StageStatus.SUCCEEDED
        )
        total_cost, cost_complete = _total_cost(stage_events)
        cost = CostSummary(
            known_subtotal_usd=total_cost,
            complete=cost_complete,
            unknown_reason=None if cost_complete else "usage_or_price_unknown",
        )
        result = AnalysisResult(
            schema_version=1,
            case_id=case_id,
            analysis_id=analysis_id,
            request_id=request_id,
            analysis_revision=revision,
            run_mode=self._run_mode,
            analysis_outcome=(
                AnalysisOutcome.COMPLETE
                if complete
                else AnalysisOutcome.MANUAL_REQUIRED
            ),
            case_state=(
                CaseState.AWAITING_REVIEW if complete else CaseState.MANUAL_REQUIRED
            ),
            trace_id=trace_id,
            policy_version="training-policy-v1",
            model_policy_version=self._model_policy_version,
            classification_prompt_version=(
                CLASSIFICATION_PROMPT_VERSION
                if classification_status is not StageStatus.SKIPPED
                else None
            ),
            classification_schema_version=(
                CLASSIFICATION_SCHEMA_VERSION
                if classification_status is not StageStatus.SKIPPED
                else None
            ),
            drafting_prompt_version=(
                DRAFTING_PROMPT_VERSION
                if drafting_status is not StageStatus.SKIPPED
                else None
            ),
            drafting_schema_version=(
                DRAFTING_SCHEMA_VERSION
                if drafting_status is not StageStatus.SKIPPED
                else None
            ),
            classification=classification,
            effective_severity=effective_severity,
            draft=draft,
            classification_stage=StageOutcomeRecord(
                status=classification_status,
                failure_code=classification_failure,
            ),
            drafting_stage=StageOutcomeRecord(
                status=drafting_status,
                failure_code=drafting_failure,
            ),
            cost=cost,
        )
        self._repository.record_completion_event(
            AnalysisCompletionEvent(
                schema_version=1,
                timestamp=self._clock(),
                event_id=str(uuid.uuid4()),
                case_id=case_id,
                analysis_id=analysis_id,
                analysis_revision=revision,
                run_mode=self._run_mode,
                input_size_bucket=_input_bucket(
                    request.complaint_text,
                    short_max=self._short_input_max,
                    medium_max=self._medium_input_max,
                ),
                policy_version=result.policy_version,
                model_policy_version=self._model_policy_version,
                analysis_outcome=result.analysis_outcome,
                duration_ms=int((time.monotonic() - started) * 1000),
                stage_event_ids=tuple(event.event_id for event in stage_events),
                cost=cost,
            )
        )
        instruments.slo_outcomes.add(
            1,
            {
                "run_mode": self._run_mode.value,
                "outcome": (
                    "good"
                    if result.analysis_outcome is AnalysisOutcome.COMPLETE
                    else "bad"
                ),
            },
        )
        self._repository.finish_analysis(result, self._clock())
        if policy_flags:
            candidate = merge(
                None,
                SignalReference(
                    source="online_rule",
                    reference_id=f"{case_id}:rev{revision}",
                    reason_code="safety_policy_review",
                ),
            )
            self._repository.merge_annotation_candidate(candidate, self._clock())
        instruments.analyses.add(
            1,
            {
                "run_mode": self._run_mode.value,
                "outcome": result.analysis_outcome.value,
            },
        )

    def _stage_event(
        self,
        *,
        case_id: str,
        analysis_id: str,
        revision: int,
        stage: Stage,
        model: str,
        complaint_text: str,
        prompt_version: str,
        schema_version: str,
        duration_ms: int,
        succeeded: bool,
        failure: FailureCode | None,
        response: ProviderResponse | None,
        attempt: int,
    ) -> StageUsageEvent:
        usage = (
            TokenUsage(
                input_tokens=None,
                output_tokens=None,
                provider_cached_input_tokens=None,
                known=False,
                unknown_reason="retry_attempt_usage_unknown",
            )
            if attempt > 1
            else _token_usage(response)
        )
        try:
            if self._run_mode is RunMode.DEMO:
                observation = CostObservation(
                    amount_usd=None,
                    complete=False,
                    pricing_version=None,
                    unknown_reason="live_price_unconfigured",
                )
            else:
                observation = calculate_usage_cost(usage, model=model)
        except CostError:
            observation = CostObservation(
                amount_usd=None,
                complete=False,
                pricing_version=None,
                unknown_reason="price_unconfigured",
            )
        if not isinstance(observation, CostObservation):
            raise TypeError("usage cost calculation returned an unexpected record")
        return StageUsageEvent(
            schema_version=1,
            timestamp=self._clock(),
            event_id=str(uuid.uuid4()),
            case_id=case_id,
            analysis_id=analysis_id,
            analysis_revision=revision,
            stage=stage,
            attempt=attempt,
            run_mode=self._run_mode,
            input_size_bucket=_input_bucket(
                complaint_text,
                short_max=self._short_input_max,
                medium_max=self._medium_input_max,
            ),
            requested_model=model,
            served_model=response.served_model if response is not None else None,
            prompt_version=prompt_version,
            stage_schema_version=schema_version,
            policy_version="training-policy-v1",
            model_policy_version=self._model_policy_version,
            succeeded=succeeded,
            error_category=None
            if succeeded
            else (failure or FailureCode.PROVIDER_ERROR).value,
            duration_ms=max(duration_ms, 0),
            usage=usage,
            cost=observation,
        )


def _token_usage(response: ProviderResponse | None) -> TokenUsage:
    if (
        response is None
        or response.input_tokens is None
        or response.output_tokens is None
    ):
        return TokenUsage(
            input_tokens=None,
            output_tokens=None,
            provider_cached_input_tokens=None,
            known=False,
            unknown_reason="provider_usage_unavailable",
        )
    return TokenUsage(
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        provider_cached_input_tokens=response.provider_cached_input_tokens,
        known=True,
        unknown_reason=None,
    )


def _record_generation_attributes(span: Span, response: ProviderResponse) -> None:
    span.set_attribute("gen_ai.request.attempt_count", response.attempts)
    if response.served_model is not None:
        span.set_attribute("gen_ai.response.model", response.served_model)
    if response.input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", response.input_tokens)
    if response.output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)


def _total_cost(events: list[StageUsageEvent]) -> tuple[Decimal, bool]:
    known_costs = [event.cost.amount_usd for event in events]
    return (
        sum((amount for amount in known_costs if amount is not None), Decimal("0")),
        all(event.cost.complete for event in events),
    )


def _record_stage_metrics(event: StageUsageEvent) -> None:
    labels = {
        "stage": event.stage.value,
        "model": event.requested_model,
        "run_mode": event.run_mode.value,
        "status": "succeeded" if event.succeeded else "failed",
    }
    instruments.stage_calls.add(1, labels)
    instruments.stage_duration.record(event.duration_ms / 1000, labels)
    if event.usage.known:
        instruments.tokens.add(
            int(event.usage.input_tokens or 0),
            {**labels, "token_type": "input"},
        )
        instruments.tokens.add(
            int(event.usage.output_tokens or 0),
            {**labels, "token_type": "output"},
        )
    if event.cost.complete and event.cost.amount_usd is not None:
        instruments.estimated_cost.add(
            float(event.cost.amount_usd),
            {**labels, "pricing_version": event.cost.pricing_version or "unknown"},
        )
    else:
        instruments.cost_unknown.add(1, labels)
