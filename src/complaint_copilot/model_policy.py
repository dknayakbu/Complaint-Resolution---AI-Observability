"""Explicit stage-to-model policy helpers for Phase B AgentOps."""

from __future__ import annotations

from collections.abc import Mapping

from complaint_copilot.contracts import ModelDecision, ModelPolicy, Stage

DEFAULT_POLICY_VERSION = "approved-stage-model-policy-v1"


class StageModelPolicy:
    """Resolution is explicit by stage; there is no severity-based fallback."""

    def __init__(
        self,
        *,
        policy_version: str = DEFAULT_POLICY_VERSION,
        approved_mapping: Mapping[Stage, str] | None = None,
    ) -> None:
        self.policy_version = policy_version
        self._mapping: dict[Stage, str] = {
            Stage.CLASSIFICATION: "gpt-4.1-mini",
            Stage.DRAFTING: "gpt-4.1-mini",
            Stage.EVALUATION: "gpt-4.1-mini",
        }
        if approved_mapping is not None:
            self._mapping.update(
                {Stage(key): value for key, value in approved_mapping.items()}
            )

    def resolve(
        self, stage: Stage, approved_config: Mapping[str, object]
    ) -> ModelDecision:
        del approved_config
        if stage not in self._mapping:
            raise ValueError(
                f"no approved model is configured for stage '{stage.value}'"
            )
        model = self._mapping[stage]
        reason = (
            f"approved stage model mapping for {stage.value}: {model}; "
            "severity is not used to route the model"
        )
        return ModelDecision(
            stage=stage,
            model=model,
            policy_version=self.policy_version,
            reason=reason,
        )


DEFAULT_STAGE_MODEL_POLICY = StageModelPolicy()


def resolve_model(
    stage: Stage,
    approved_config: Mapping[str, object] | None = None,
    *,
    policy: ModelPolicy | None = None,
) -> ModelDecision:
    active_policy = policy or DEFAULT_STAGE_MODEL_POLICY
    normalized_config = {} if approved_config is None else dict(approved_config)
    return active_policy.resolve(stage, normalized_config)


__all__ = [
    "DEFAULT_POLICY_VERSION",
    "DEFAULT_STAGE_MODEL_POLICY",
    "StageModelPolicy",
    "resolve_model",
]
