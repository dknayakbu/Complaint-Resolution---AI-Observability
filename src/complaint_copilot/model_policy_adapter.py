"""Phase A's fixed-model adapter for the shared B-owned policy interface."""

from collections.abc import Mapping

from complaint_copilot.contracts import ModelDecision, Stage


class FixedModelPolicy:
    """Use one explicitly configured model for every stage."""

    def __init__(
        self, model: str, policy_version: str = "fixed-model-policy-v1"
    ) -> None:
        if not model.strip() or not policy_version.strip():
            raise ValueError("model and policy version must be non-empty")
        self._model = model
        self._policy_version = policy_version

    def resolve(
        self, stage: Stage, approved_config: Mapping[str, object]
    ) -> ModelDecision:
        del approved_config
        return ModelDecision(
            stage=stage,
            model=self._model,
            policy_version=self._policy_version,
            reason="one fixed configured model for Phase A",
        )
