"""Streamlit interface for the synthetic complaint and reviewer journey."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

import streamlit as st

API_URL = os.getenv("COPILOT_API_URL", "http://localhost:8000").rstrip("/")
REVIEWER_TOKEN = os.getenv("REVIEWER_TOKEN", "fixture-reviewer-token")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "fixture-internal-token")
API_REQUEST_TIMEOUT_SECONDS = 420


def _request(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(
            request, timeout=API_REQUEST_TIMEOUT_SECONDS
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"API is unavailable: {error.reason}") from error


def main() -> None:
    st.set_page_config(page_title="Complaint Resolution Co-Pilot", layout="wide")
    st.title("Complaint Resolution Co-Pilot")
    try:
        mode = _request("GET", "/api/mode")
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    if mode["mode"] == "fixture":
        st.warning(
            "FIXTURE MODE — scripted synthetic responses; not an OpenAI/model demo."
        )
    else:
        st.error(
            "LIVE MODE — synthetic text is sent to OpenAI and calls may cost money."
        )
        st.caption(
            "Approved limits: "
            f"{mode['live_max_requests']} workflow requests, "
            f"{mode['live_max_calls']} provider attempts, "
            f"{mode['live_max_tokens']} reserved tokens, "
            f"USD {mode['live_max_cost_usd']} reserved cost. "
            "A successful complaint normally requires two provider calls."
        )

    try:
        model_policy = _request("GET", "/api/model-policy")
        sli = _request("GET", "/api/operations/slo")
        st.sidebar.subheader("Runtime policy and SLI")
        st.sidebar.caption(f"Policy: {model_policy['policy_version']}")
        st.sidebar.json(model_policy["stage_models"])
        st.sidebar.metric(
            "Latest-30 eligible outcomes",
            f"{sli['eligible_samples']}/{sli['window_size']}",
        )
        if sli["status"] == "measured":
            st.sidebar.metric("Observed good rate", f"{float(sli['good_rate']):.1%}")
            st.sidebar.caption(f"{sli['good']} good / {sli['bad']} manual-required")
        else:
            st.sidebar.warning("SLI sample is insufficient; no green status claimed.")
    except (KeyError, RuntimeError) as error:
        st.sidebar.error(f"Runtime status unavailable: {error}")

    intake_tab, review_tab, replay_tab, alerts_tab = st.tabs(
        ["Complaint intake", "Reviewer queue", "Synthetic replays", "Alert inbox"]
    )
    with intake_tab:
        _intake(live_mode=mode["mode"] == "live")
    with review_tab:
        _review()
    with replay_tab:
        _replays()
    with alerts_tab:
        _alerts()


def _intake(*, live_mode: bool = False) -> None:
    if live_mode:
        st.caption(
            "Live mode sends this invented complaint to the configured OpenAI "
            "classification and drafting models. Fixture controls are disabled."
        )
        complaint_label = "Synthetic complaint sent to live models"
    else:
        complaint_label = "Synthetic complaint text"
    complaint = st.text_area(
        complaint_label,
        placeholder="Enter an invented complaint; do not enter customer data.",
        max_chars=20_000,
    )
    source_sample_id = None
    if not live_mode:
        source_sample_id = st.text_input(
            "Optional synthetic fixture ID",
            help="Use scene-2-controlled-raw-miss to rehearse a controlled "
            "classification miss, or synthetic-provider-timeout for a fixture "
            "failure.",
        )
    if st.button("Submit for analysis", type="primary"):
        if not complaint.strip():
            st.error("Enter non-empty synthetic complaint text.")
            return
        try:
            case = _request(
                "POST",
                "/api/cases",
                payload={
                    "complaint_text": complaint,
                    "synthetic": True,
                    "source_sample_id": (
                        source_sample_id.strip()
                        if source_sample_id and source_sample_id.strip()
                        else None
                    ),
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            st.session_state["selected_case"] = case["case_id"]
            st.success(f"Saved synthetic case {case['case_id']}")
            _show_case(case, view="intake")
        except RuntimeError as error:
            st.error(str(error))


def _review() -> None:
    notice = st.session_state.pop("review_notice", None)
    if isinstance(notice, str):
        st.success(notice)
    try:
        cases = _request("GET", "/api/cases")
        pending = [case for case in cases if case["state"] == "awaiting_review"]
        if not pending:
            st.info("No cases are awaiting review.")
            _show_queue()
            return
        labels = {
            f"{case['case_id']} (revision {case['current_revision']})": case
            for case in pending
        }
        selected_label = st.selectbox("Pending case", list(labels))
        case = labels[selected_label]
        _show_case(case, view="review")
        latest = case["analyses"][-1]
        classification = latest["result"]["classification"]
        reason = st.text_input("Review reason", value="Synthetic training review.")
        if st.button("Approve current revision and route"):
            try:
                routed = _request(
                    "POST",
                    f"/api/cases/{case['case_id']}/review",
                    payload={
                        "expected_case_version": case["version"],
                        "analysis_revision": latest["revision"],
                        "reason": reason,
                        "category": classification["category"],
                        "queue": classification["category"],
                    },
                    headers={"Authorization": f"Bearer {REVIEWER_TOKEN}"},
                )
                st.session_state["review_notice"] = (
                    "Approved; one simulated queue entry created: "
                    f"{routed['queue_entry_id']}"
                )
                st.rerun()
            except RuntimeError as error:
                st.error(str(error))

        _feedback_and_adjudication(case, latest)
    except RuntimeError as error:
        st.error(str(error))

    _show_queue()


def _show_queue() -> None:
    st.subheader("Simulated queue")
    try:
        st.dataframe(_request("GET", "/api/queue"))
    except RuntimeError as error:
        st.error(str(error))


def _feedback_and_adjudication(case: dict[str, Any], latest: dict[str, Any]) -> None:
    st.subheader("Revision-linked feedback")
    rating = st.radio(
        "Was this analysis useful?",
        ["up", "down"],
        horizontal=True,
        key=f"rating-{case['case_id']}",
    )
    feedback_note = st.text_input("Feedback note", key=f"feedback-{case['case_id']}")
    if st.button("Save feedback", key=f"save-feedback-{case['case_id']}"):
        try:
            _request(
                "POST",
                f"/api/cases/{case['case_id']}/feedback",
                payload={
                    "analysis_revision": latest["revision"],
                    "rating": rating,
                    "note": feedback_note or None,
                },
                headers={"Authorization": f"Bearer {REVIEWER_TOKEN}"},
            )
            st.success("Feedback linked to the displayed analysis revision.")
        except RuntimeError as error:
            st.error(str(error))

    if rating != "down":
        return
    try:
        annotations = _request("GET", "/api/annotations")
    except RuntimeError as error:
        st.error(str(error))
        return
    candidates = [
        row
        for row in annotations
        if row["case_id"] == case["case_id"] and row["status"] == "pending"
    ]
    if not candidates:
        st.info("No pending annotation candidate exists for this case.")
        return
    candidate = candidates[0]
    st.caption(
        f"Pending annotation: {candidate['annotation_id']} "
        f"(analysis revision {candidate['analysis_revision']})"
    )
    categories = [
        "accounts",
        "cards_payments",
        "service_access",
        "lending",
        "fraud_scams",
        "other",
    ]
    result = latest["result"]
    classification = result["classification"]
    category = st.selectbox(
        "Adjudicated category",
        categories,
        index=categories.index(classification["category"]),
        key=f"label-category-{case['case_id']}",
    )
    severity = st.selectbox(
        "Adjudicated severity",
        [1, 2, 3],
        index=[1, 2, 3].index(result["effective_severity"]),
        key=f"label-severity-{case['case_id']}",
    )
    if st.button(
        "Save authorized adjudicated label", key=f"adjudicate-{case['case_id']}"
    ):
        try:
            saved = _request(
                "POST",
                f"/api/annotations/{candidate['annotation_id']}/adjudicate",
                payload={
                    "expected_case_version": case["version"],
                    "analysis_revision": candidate["analysis_revision"],
                    "case_id": case["case_id"],
                    "category": category,
                    "severity": severity,
                    "queue": category,
                    "draft_rubric_assessment": "Synthetic reviewer assessment.",
                    "reason": "Synthetic demo adjudication.",
                },
                headers={"Authorization": f"Bearer {REVIEWER_TOKEN}"},
            )
            label_id = saved.get("label_id", "saved")
            st.session_state["review_notice"] = f"Adjudicated label {label_id} saved."
            st.rerun()
        except RuntimeError as error:
            st.error(str(error))


def _replays() -> None:
    st.caption("Every replay uses synthetic fixtures and existing Phase B/C logic.")
    columns = st.columns(4)
    for column, scenario in zip(
        columns, ("drift", "cost", "quality", "slo"), strict=True
    ):
        with column:
            if st.button(f"Run {scenario} replay"):
                try:
                    result = _request(
                        "POST",
                        f"/internal/demo/replay/{scenario}",
                        headers={
                            "X-Internal-Token": INTERNAL_TOKEN,
                            "Idempotency-Key": str(uuid.uuid4()),
                        },
                    )
                    st.json(result)
                except RuntimeError as error:
                    st.error(str(error))


def _alerts() -> None:
    st.caption("Synthetic local inbox only; no external notification is sent.")
    if st.button("Send a synthetic firing alert"):
        try:
            result = _request(
                "POST",
                "/internal/alerts",
                payload={
                    "fingerprint": f"ui-demo-{uuid.uuid4()}",
                    "status": "firing",
                    "priority": "P2",
                    "title": "Synthetic demo alert",
                },
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            st.success(f"Synthetic alert accepted: {result}")
        except RuntimeError as error:
            st.error(str(error))
    try:
        st.dataframe(_request("GET", "/api/alerts"))
    except RuntimeError as error:
        st.error(str(error))


def _show_case(case: dict[str, Any], *, view: str) -> None:
    st.write(f"**State:** {case['state']} · **Revision:** {case['current_revision']}")
    st.write("**Complaint:**", case["complaint_text"])
    if not case["analyses"]:
        return
    latest = case["analyses"][-1]
    result = latest.get("result")
    if not isinstance(result, dict):
        st.warning("Analysis result is unavailable.")
        return
    classification = result.get("classification")
    if isinstance(classification, dict):
        st.write(
            f"**Category:** {classification['category']} · "
            f"**Model severity:** SEV{classification['model_severity']} · "
            f"**Effective severity:** SEV{result['effective_severity']}"
        )
    classification_stage = result.get("classification_stage")
    drafting_stage = result.get("drafting_stage")
    if isinstance(classification_stage, dict) and isinstance(drafting_stage, dict):
        st.caption(
            "Generation stages — "
            f"classification: {classification_stage['status']}; "
            f"drafting: {drafting_stage['status']}."
        )
    cost = result.get("cost")
    if isinstance(cost, dict):
        known_cost = cost.get("known_subtotal_usd")
        if known_cost is not None:
            qualifier = (
                "complete estimate"
                if cost.get("complete")
                else "known subtotal; some cost is unknown"
            )
            pricing_basis = (
                "at the approved live rate ceiling"
                if result.get("run_mode") == "demo"
                else "using fixture pricing"
            )
            st.caption(
                f"Estimated model cost: USD {known_cost} ({qualifier}, "
                f"{pricing_basis}; not a provider invoice)."
            )
    if result.get("draft"):
        st.text_area(
            "Draft plus fixed wording",
            result["draft"],
            disabled=True,
            key=f"draft-{view}-{case['case_id']}",
        )
    else:
        st.error(
            "Manual-required: no acknowledgement was generated. "
            f"Failure: {latest.get('failure_code') or 'see stage status'}"
        )
    st.caption(f"Trace reference: {latest['trace_id']}")


if __name__ == "__main__":
    main()
