"""Online evaluation helpers for Phase C."""

from __future__ import annotations

from collections.abc import Mapping

from complaint_copilot.contracts import (
    AnalysisResult,
    EvaluationResult,
    EvaluationScore,
    EvaluationSource,
    EvaluationStatus,
)


class OnlineRuleEvaluator:
    """A rule-based online evaluator that never calls a model.

    It is intentionally conservative: without a known label, the result is
    reported as unknown rather than pretending that a real-quality check passed.
    """

    def __init__(self, evaluator_version: str = "online-rule-v1") -> None:
        self.evaluator_version = evaluator_version

    def check(
        self,
        result: AnalysisResult,
        policy_context: Mapping[str, object],
    ) -> EvaluationResult:
        raw_signals = policy_context.get("policy_flags", ())
        signals = list(raw_signals) if isinstance(raw_signals, (list, tuple)) else []
        if result.classification is None or result.effective_severity is None:
            return EvaluationResult(
                schema_version=1,
                case_id=result.case_id,
                analysis_id=result.analysis_id,
                analysis_revision=result.analysis_revision,
                evaluator_version=self.evaluator_version,
                rubric_version=str(
                    policy_context.get("rubric_version", "policy-rubric-v1")
                ),
                source=EvaluationSource.ONLINE_RULE,
                status=EvaluationStatus.UNKNOWN,
                findings=(
                    "classification_missing",
                    "online_rule_requires_label_for_quality_assertion",
                ),
                scores=(EvaluationScore(name="policy_coverage", value=None),),
                reason_code="no_label_available",
            )

        findings = ["classification_recorded", "policy_flags_considered"]
        if signals:
            findings.extend(f"policy_flag:{signal}" for signal in signals)

        if not policy_context.get("expected_category") and not policy_context.get(
            "expected_severity"
        ):
            return EvaluationResult(
                schema_version=1,
                case_id=result.case_id,
                analysis_id=result.analysis_id,
                analysis_revision=result.analysis_revision,
                evaluator_version=self.evaluator_version,
                rubric_version=str(
                    policy_context.get("rubric_version", "policy-rubric-v1")
                ),
                source=EvaluationSource.ONLINE_RULE,
                status=EvaluationStatus.UNKNOWN,
                findings=tuple(findings),
                scores=(EvaluationScore(name="policy_coverage", value=None),),
                reason_code="no_label_available",
            )

        status = EvaluationStatus.PASS
        reason_code = "policy_rule_passed"
        if result.analysis_outcome.value == "manual_required":
            status = EvaluationStatus.FAIL
            reason_code = "manual_required_requires_human_review"
        elif result.draft is None and result.drafting_stage.status.value == "failed":
            status = EvaluationStatus.FAIL
            reason_code = "drafting_failed"

        return EvaluationResult(
            schema_version=1,
            case_id=result.case_id,
            analysis_id=result.analysis_id,
            analysis_revision=result.analysis_revision,
            evaluator_version=self.evaluator_version,
            rubric_version=str(
                policy_context.get("rubric_version", "policy-rubric-v1")
            ),
            source=EvaluationSource.ONLINE_RULE,
            status=status,
            findings=tuple(findings),
            scores=(EvaluationScore(name="policy_coverage", value=None),),
            reason_code=reason_code,
        )
