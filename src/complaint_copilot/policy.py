"""Phase A validation of model records and safety invariants."""

import json
import re
from collections.abc import Mapping

from complaint_copilot.contracts import (
    Category,
    Classification,
    ContractViolation,
    QueueKey,
    Severity,
)

_FINANCIAL_HARM_PATTERNS = (
    re.compile(
        r"\b(?:payment|money|funds|amount|balance)\b.{0,30}\b"
        r"(?:taken|stolen|withdrawn|missing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:lost|loss of|stolen|taken|withdrawn|missing)\b"
        r"(?:\W+\w+){0,3}\W+(?:money|funds|cash|£\s?\d|gbp|payment|transaction)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:money|funds|cash)\b.{0,30}\b(?:taken|stolen|withdrawn|missing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:unauthori[sz]ed|fraudulent)\b.{0,24}\b"
        r"(?:payment|transaction|transfer|withdrawal|charge)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:charged|debited)\b.{0,24}\b(?:twice|incorrectly|in error|by mistake)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:payment|charge|transaction)\b.{0,30}\bwithout "
        r"(?:my )?(?:permission|consent|authori[sz]ation)\b",
        re.IGNORECASE,
    ),
)
_FINANCIAL_NEGATION = re.compile(
    r"\b(?:not|never|no longer|did not|didn't|do not|don't|"
    r"have not|haven't|has not|hasn't)\b(?:\W+\w+){0,3}\W+"
    r"(?:lost|lose|stolen|taken|missing|withdrawn|charged|debited)\b",
    re.IGNORECASE,
)
_NO_FINANCIAL_HARM = re.compile(
    r"\bno (?:immediate )?(?:financial harm|money (?:was )?lost|"
    r"funds (?:were )?lost)\b",
    re.IGNORECASE,
)
_LOSS_OF_ESSENTIAL_FUNDS = re.compile(
    r"\b(?:cannot|can't|unable to)\b(?:\W+\w+){0,8}\W+"
    r"(?:money|funds|cash)\b.{0,40}\b(?:food|rent|medicine|essentials?)\b"
    r"|\bimmediate financial harm\b",
    re.IGNORECASE,
)
_DISCRIMINATION = re.compile(
    r"\bdiscriminat(?:e|ed|ion|ory)\b"
    r"|\btreated differently\b.{0,48}\b(?:because|due to|based on)\b",
    re.IGNORECASE,
)
_DISCRIMINATION_NEGATION = re.compile(
    r"\b(?:not|never|no)\b(?:\W+\w+){0,3}\W+"
    r"(?:discriminat(?:e|ed|ion)|treated differently)\b",
    re.IGNORECASE,
)


def validate_classification(
    payload: str | Mapping[str, object], complaint_text: str
) -> Classification:
    try:
        data: object = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError as error:
        raise ContractViolation("classification output is not valid JSON") from error
    if not isinstance(data, Mapping):
        raise ContractViolation("classification output must be a JSON object")
    classification = Classification.from_mapping(data)
    for evidence in classification.evidence:
        if (
            evidence.end > len(complaint_text)
            or complaint_text[evidence.start : evidence.end] != evidence.quote
        ):
            raise ContractViolation(
                "classification evidence offsets and quote must match complaint text"
            )
    return classification


def apply_safeguards(
    complaint_text: str, classification: Classification
) -> tuple[Severity, tuple[str, ...]]:
    """Promote covered, positively asserted harm; never demote model urgency."""
    signals: list[str] = []
    financial_harm = any(
        pattern.search(complaint_text) for pattern in _FINANCIAL_HARM_PATTERNS
    ) or bool(_LOSS_OF_ESSENTIAL_FUNDS.search(complaint_text))
    if (
        financial_harm
        and not _FINANCIAL_NEGATION.search(complaint_text)
        and not _NO_FINANCIAL_HARM.search(complaint_text)
    ):
        signals.append("financial_harm_signal")

    discrimination = bool(_DISCRIMINATION.search(complaint_text))
    if discrimination and not _DISCRIMINATION_NEGATION.search(complaint_text):
        signals.append("discrimination_signal")

    effective = classification.model_severity
    if signals:
        effective = min(effective, Severity.SEV1)
    return effective, tuple(signals)


def queue_for_category(category: Category) -> QueueKey:
    return QueueKey(category.value)


def validate_draft(payload: str | Mapping[str, object]) -> str:
    try:
        data: object = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError as error:
        raise ContractViolation("draft output is not valid JSON") from error
    if not isinstance(data, Mapping):
        raise ContractViolation("draft output must be a JSON object")
    if set(data) != {"draft"}:
        raise ContractViolation("draft output may contain only personalized prose")
    draft = data["draft"]
    if not isinstance(draft, str) or not draft.strip():
        raise ContractViolation("draft must be non-empty text")
    if len(draft) > 20_000:
        raise ContractViolation("draft exceeds its maximum length")
    if any(ord(char) < 32 and char not in "\n\t\r" for char in draft):
        raise ContractViolation("draft contains unsupported control characters")
    return draft.strip()
