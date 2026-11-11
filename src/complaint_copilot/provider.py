"""Bounded generation adapters without implicit live/fixture fallbacks."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from complaint_copilot.contracts import Stage


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    served_model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_cached_input_tokens: int | None = None
    attempts: int = 1

    def __post_init__(self) -> None:
        if type(self.attempts) is not int or self.attempts < 1:
            raise ValueError("provider response attempts must be a positive integer")


class ProviderFailure(RuntimeError):
    def __init__(
        self, code: str, *, retryable: bool, usage: ProviderResponse | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.usage = usage
        self.attempts = 1


class Provider(Protocol):
    def generate(
        self,
        stage: Stage | None,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> ProviderResponse: ...


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def generate(
        self,
        stage: Stage | None,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> ProviderResponse:
        del stage
        try:
            response = self._client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except APITimeoutError as error:
            raise ProviderFailure("provider_timeout", retryable=True) from error
        except APIConnectionError as error:
            raise ProviderFailure("provider_timeout", retryable=True) from error
        except APIStatusError as error:
            retryable = error.status_code == 429 or error.status_code >= 500
            code = (
                "provider_rate_limited"
                if error.status_code == 429
                else "provider_error"
            )
            raise ProviderFailure(code, retryable=retryable) from error
        except Exception as error:
            raise ProviderFailure("provider_error", retryable=False) from error

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice is not None else None
        if not isinstance(content, str) or not content:
            raise ProviderFailure("provider_empty_response", retryable=False)

        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", None)
        return ProviderResponse(
            content=content,
            served_model=response.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            provider_cached_input_tokens=cached_tokens,
        )


class RetryingProvider:
    def __init__(
        self,
        provider: Provider,
        max_attempts: int,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self._provider = provider
        self._max_attempts = max_attempts
        self._sleep = sleeper

    def generate(
        self,
        stage: Stage | None,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> ProviderResponse:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._provider.generate(
                    stage, model, system_prompt, user_prompt
                )
                return replace(response, attempts=attempt)
            except ProviderFailure as error:
                error.attempts = attempt
                if not error.retryable or attempt == self._max_attempts:
                    raise
                self._sleep(min(0.1 * (2 ** (attempt - 1)), 0.5))
        raise AssertionError("bounded provider retry loop exhausted unexpectedly")


class FixtureProvider:
    """Explicit, credential-free provider for labeled fixture-mode use."""

    def __init__(
        self,
        responses: Mapping[Stage | None, Sequence[ProviderResponse | ProviderFailure]]
        | None = None,
    ) -> None:
        self.calls: list[tuple[Stage | None, str, str]] = []
        self._responses = {
            key: list(values) for key, values in (responses or {}).items()
        }

    def generate(
        self,
        stage: Stage | None,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> ProviderResponse:
        self.calls.append((stage, model, user_prompt))
        configured = self._responses.get(stage)
        if configured:
            response = configured.pop(0)
            if isinstance(response, ProviderFailure):
                raise response
            return response

        if stage is None:
            return ProviderResponse(
                json.dumps(
                    {
                        "category": "accounts",
                        "severity": 3,
                        "draft": "Thank you for describing the account access issue.",
                    }
                ),
                model,
            )
        if stage is Stage.CLASSIFICATION:
            try:
                payload = json.loads(user_prompt)
                complaint = payload["complaint_text"]
                source_sample_id = payload.get("source_sample_id")
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                raise ProviderFailure(
                    "fixture_input_invalid", retryable=False
                ) from error
            if not isinstance(complaint, str) or not complaint:
                raise ProviderFailure("fixture_input_invalid", retryable=False)
            if source_sample_id in {
                "synthetic-provider-timeout",
                "test-provider-timeout",
            }:
                raise ProviderFailure("provider_timeout", retryable=False)
            if source_sample_id == "scene-2-controlled-raw-miss":
                category, severity = "other", 3
            else:
                category, severity = _fixture_classification(complaint)
            quote = complaint[: min(len(complaint), 1200)]
            return ProviderResponse(
                json.dumps(
                    {
                        "category": category,
                        "model_severity": severity,
                        "evidence": [{"start": 0, "end": len(quote), "quote": quote}],
                        "decision_summary": (
                            "Scripted fixture classification; human review required."
                        ),
                    }
                ),
                model,
            )
        if stage is Stage.DRAFTING:
            try:
                payload = json.loads(user_prompt)
                complaint = str(payload["complaint_text"]).casefold()
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                raise ProviderFailure(
                    "fixture_input_invalid", retryable=False
                ) from error
            if "replacement" in complaint and "card" in complaint:
                draft = (
                    "Thank you for explaining that your replacement debit card "
                    "arrived after the expected date while your current card works."
                )
            elif "duplicate" in complaint or "debited" in complaint:
                draft = (
                    "Thank you for explaining the duplicate debit and its effect "
                    "on the money you need for rent."
                )
            else:
                draft = (
                    "Thank you for describing your concern. We will review the "
                    "information you provided."
                )
            return ProviderResponse(
                json.dumps({"draft": draft}),
                model,
            )
        raise ProviderFailure("unsupported_fixture_stage", retryable=False)


def _fixture_classification(complaint: str) -> tuple[str, int]:
    """Map known synthetic story phrases to scripted, non-model fixture results."""
    lowered = complaint.casefold()
    if "disability accommodation" in lowered or "discrimination" in lowered:
        return "discrimination", 3
    if "scam" in lowered or "verification code" in lowered:
        return "fraud_scams", 3
    if "replacement card" in lowered or "duplicate" in lowered or "debit" in lowered:
        return "cards_payments", 3
    if "credit" in lowered or "mortgage" in lowered or "loan" in lowered:
        return "lending", 3
    if "cannot access" in lowered or "locked out" in lowered or "portal" in lowered:
        return "service_access", 3
    if "account" in lowered or "statement" in lowered:
        return "accounts", 3
    return "other", 3
