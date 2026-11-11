from complaint_copilot.telemetry import make_metric, redact_labels, redact_value


def test_redaction_masks_sensitive_metric_labels() -> None:
    labels = {
        "case_id": "case-123",
        "prompt": "secret prompt",
        "error": "exception: stack trace",
        "safe": "keep me",
    }
    redacted = redact_labels(labels)
    assert redacted["case_id"] == "<redacted>"
    assert redacted["prompt"] == "<redacted>"
    assert redacted["error"] == "<redacted>"
    assert redacted["safe"] == "keep me"


def test_redact_value_keeps_non_sensitive_values_but_redacts_sensitive_text() -> None:
    assert redact_value("normal label") == "normal label"
    assert redact_value("This complaint was rejected") == "<redacted>"
    assert redact_value("   ") == "<redacted>"


def test_make_metric_emits_explicit_metric_records() -> None:
    metric = make_metric(
        "cost.total", 1.25, labels={"run_mode": "fixture", "team": "ops"}
    )
    assert metric.name == "cost.total"
    assert metric.value == 1.25
    assert metric.labels["run_mode"] == "fixture"
    assert metric.labels["team"] == "ops"
