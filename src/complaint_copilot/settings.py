"""Validated environment configuration for Phase A."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    mode: str = "fixture"
    database_path: Path = Path("complaint-copilot.sqlite3")
    model: str = "gpt-4o-mini"
    classification_model: str | None = None
    drafting_model: str | None = None
    evaluation_model: str | None = None
    openai_api_key: str | None = None
    reviewer_token: str = "fixture-reviewer-token"
    internal_token: str = "fixture-internal-token"
    request_timeout_seconds: float = 20.0
    max_provider_attempts: int = 2
    short_input_max: int | None = None
    medium_input_max: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"fixture", "live"}:
            raise ValueError("APP_MODE must be 'fixture' or 'live'")
        if not self.model.strip():
            raise ValueError("MODEL_NAME must be non-empty")
        for stage, model in (
            ("CLASSIFICATION_MODEL", self.classification_model),
            ("DRAFTING_MODEL", self.drafting_model),
            ("EVALUATION_MODEL", self.evaluation_model),
        ):
            if model is not None and not model.strip():
                raise ValueError(f"{stage} must be non-empty when configured")
        if not 0 < self.request_timeout_seconds <= 60:
            raise ValueError("provider timeout must be between 0 and 60 seconds")
        if not 1 <= self.max_provider_attempts <= 3:
            raise ValueError("provider attempts must be between 1 and 3")
        if self.mode == "live":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required in live mode")
            if not self.reviewer_token or self.reviewer_token.startswith("fixture-"):
                raise ValueError("REVIEWER_TOKEN must be set in live mode")
            if not self.internal_token or self.internal_token.startswith("fixture-"):
                raise ValueError("INTERNAL_TOKEN must be set in live mode")
            if (
                self.short_input_max is None
                or self.medium_input_max is None
                or self.short_input_max <= 0
                or self.medium_input_max <= self.short_input_max
            ):
                raise ValueError(
                    "live mode requires ordered SHORT_INPUT_MAX and MEDIUM_INPUT_MAX"
                )

    @classmethod
    def from_env(cls) -> "AppSettings":
        mode = os.getenv("APP_MODE", "fixture").strip().lower()
        return cls(
            mode=mode,
            database_path=Path(os.getenv("DATABASE_PATH", "complaint-copilot.sqlite3")),
            model=os.getenv("MODEL_NAME", "gpt-4o-mini").strip(),
            classification_model=_optional_model_env("CLASSIFICATION_MODEL"),
            drafting_model=_optional_model_env("DRAFTING_MODEL"),
            evaluation_model=_optional_model_env("EVALUATION_MODEL"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            reviewer_token=os.getenv(
                "REVIEWER_TOKEN",
                "fixture-reviewer-token" if mode == "fixture" else "",
            ),
            internal_token=os.getenv(
                "INTERNAL_TOKEN",
                "fixture-internal-token" if mode == "fixture" else "",
            ),
            request_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "20")),
            max_provider_attempts=int(os.getenv("PROVIDER_MAX_ATTEMPTS", "2")),
            short_input_max=_optional_int_env("SHORT_INPUT_MAX"),
            medium_input_max=_optional_int_env("MEDIUM_INPUT_MAX"),
        )


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error


def _optional_model_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()
