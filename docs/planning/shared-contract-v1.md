# Complaint Co-Pilot - Shared Contract v1

Planning specification for the three parallel workstreams in [the main plan](plan.md). This is not implemented code. Share all six documents together; [README](README.md) explains the blank-repository and PR workflow.

## 1. Freeze procedure and ownership

- Start with a blank new target repository, initialized only with a minimal README anchor on `main`. Do not reuse the host application's package, contracts or dependencies.
- Person A creates **PR-0** on `chore/foundation`: implement shared types in `src\complaint_copilot\contracts.py`, package/lockfile, test/lint/type configuration and fixture vectors. A/B/C review and merge this foundation before phase branches are created.
- PR-0 must be runnable without agents, UI, persistence, observability services or API credentials. Its fixture tests check record validation, not unimplemented end-to-end behavior.
- Include package/test configuration and fixtures for success, SEV1 promotion, and drafting failure after successful classification.
- All owners use the same classes and contract fixtures. Do not copy private alternatives into each subsystem.
- Unresolved details must be resolved at bootstrap, not silently defaulted. Changes to required fields/enums are reviewed by all three and accompanied by compatibility fixtures.
- v1 uses ordinary typed functions/records and dependency injection. No event bus, plugin framework or service registry is needed.
- Only A owns production storage/migrations, API authorization and active-case state changes. B/C return records or call A's agreed storage adapter.
- After PR-0, A/B/C each opens its own module PR from the merged foundation. Test/merge order is **PR-0 -> PR-A -> PR-B -> PR-C -> PR-I**, with module development parallel after PR-0. Refresh and retest against current `main` before every merge.

## 2. Common semantics

| Field / concept | v1 meaning |
| --- | --- |
| `schema_version` | Literal `1` on exchanged result/event records |
| `case_id`, `analysis_id`, `request_id`, `event_id` | Opaque identifiers; unique event IDs make observation/import idempotent |
| `analysis_revision` | Positive integer; review/feedback must reference the exact revision |
| `run_mode` | `demo`, `fixture`, `evaluation`, `fault`, `experiment`; assigned by trusted application/runner configuration |
| `stage` | `classification`, `drafting`, `evaluation`; normal complaint processing uses the first two |
| `model_policy` | `fixed` or `stage_tiered`, with explicit approved configuration version |
| `input_size_bucket` | Bounded `short`, `medium`, `long` bucket from A's validated raw-text length; thresholds jointly frozen in operations config, never inferred from complaint instructions |
| Category / queue key | `cards_payments`, `accounts`, `fraud_scams`, `lending`, `service_access`, `discrimination`, `other` |
| `complaint_severity` | Integer `1..3`; `1` is most urgent. Preserve `model_severity` and `effective_severity` separately |
| `incident_priority` | `P1`, `P2`, `P3`; distinct type and purpose from complaint severity |
| Missing observation | Explicit `null`/unknown plus reason; never silently zero, good, pass or low priority |
| Timestamp / duration | UTC timestamps and nonnegative measured duration; inject a clock in tests |
| Costs | Decimal USD internally; decimal strings or null on the wire, with pricing version and completeness flag |
| Versions | Explicit classification/drafting prompt and schema versions, policy/model-policy version and dataset/label version where applicable |

No raw complaint, draft, evidence quote, customer/user identifier or arbitrary error text is a metric label. Opaque case/revision references belong in restricted records and traces, not metric labels.

## 3. Application and stage records

**Analysis request:** bounded `complaint_text`, `synthetic=true`, optional opaque `source_sample_id`. HTTP idempotency key is separate. Ground-truth fields are forbidden. Authenticated actor, selected model policy and run mode are supplied by trusted context, never instructions inside the complaint.

**Classification result:** category, model severity, supporting evidence spans/offsets and concise decision summary. A validates evidence, applies policy and stores effective severity, policy flags and proposed queue. No hidden chain-of-thought.

**Draft result:** personalized prose only. It cannot supply replacement category, severity, queue, approval or closed-case status. A appends approved fixed wording and enforces release invariants.

**Analysis result:** common identifiers/versions; explicit `analysis_outcome` (`complete` or `manual_required`); retained classification if available; nullable draft; stage outcomes and controlled failure codes; case state; linked trace; known-cost subtotal and `cost_complete`. Failed classification skips drafting; failed drafting retains classification/urgency. Normal success is two logical calls, no tool loop.

The controlled stage failure codes are `classification_invalid`, `drafting_invalid`, `provider_timeout`, and `provider_error`. `provider_timeout` is reserved for exhausted timeouts; `provider_error` is the single terminal code for other provider failures after bounded retries, including rate limits and provider/API errors. Ordinary request validation and authorization failures are API errors, not analysis failure codes. Bounded detail may be recorded separately in the stage event's `error_category`; provider exception text is not exposed.

**Stage usage event:** event/case/analysis/revision references; stage/attempt; run mode; input-size bucket; requested/served model; prompt/schema/policy/model-policy versions; success/error category; duration; reported input/output/provider-cached tokens or null; usage-known flag. B calculates attributable estimated cost from a pinned price table. A stores the event and derived cost record once. Provider-reported cached-input tokens are billing details, not an application response cache.

**Analysis completion event:** unique event ID; case/analysis/revision; run mode; input-size bucket; policy versions; final analysis outcome; measured workflow duration; stage event references; total known-cost subtotal; cost-complete flag. B must not double-count stage cost again when consuming completion events.

All billed/reported attempts count. An error with unknown usage is not a free call. A successful classification is not automatically repeated after drafting failure.

## 4. Function boundaries

These are small interfaces to freeze, not a mandatory object hierarchy:

| A calls / owns | B or C provides |
| --- | --- |
| Resolve a configured model by stage before provider invocation | B: `model_policy.resolve(stage, approved_config) -> ModelDecision` containing model, policy version and reason |
| Validate/reserve/release model-workflow capacity | B: bounded capacity helper; A enforces busy response before intake/provider execution and releases capacity on every exit |
| Price and record a stage/completion observation | B: pure cost calculation and telemetry functions; recording fakes work before B integration |
| Request online checks of a completed result | C: `online_eval.check(result, policy_context) -> EvaluationResult`; no hidden model call |
| Merge evaluation/human review signals | C: `feedback.merge(existing_candidate, signal) -> AnnotationCandidate`; A persists returned state transactionally |
| Rank pending annotation items | C: deterministic safety-first ordering; no DB writes |
| Compute offline quality and input drift | C: functions over explicit inputs/labels/windows; missing labels/samples return unknown/ineligible |
| Adapt Grafana webhook to incident events | B: validated adapter and priority/episode mapping; A persists idempotently |

Every implementation imports shared types. A's fakes record calls and explicit fixture outcomes; they are not silent live-mode defaults. Imports and fixture tests must not instantiate a paid client or require credentials.

## 5. Evaluation, feedback and labels

**Evaluation result:** case/analysis/revision, evaluator/rubric version, source (`online_rule`, `offline_label`, `optional_judge`), status (`pass`, `fail`, `unknown`), bounded findings, nullable scores and reason code. Severity/category correctness is unknown without an adjudicated label. Optional judge failure is unknown + evaluator error.

**Feedback input:** exact case/revision, rating (`up`, `down`) and bounded note; trusted actor/source added by API. Ratings cannot change authoritative labels, approval or routing.

**Annotation candidate:** key `(case_id, analysis_revision)`, set of source/reason references, priority, evidence links, status (`pending`, `adjudicated`). Merge duplicate signals; retain all reasons. Do not attach a finding from a different revision.

**Adjudicated label:** category, severity, queue, draft rubric assessment, reviewer, reason, label version and superseded-label link where applicable. Authorization is enforced by A's review/adjudication transaction. One correction does not create two label revisions through separate endpoints.

Inputs and label files are separate. Joining is permitted only inside the evaluator. Frozen holdout and showcase/development families cannot overlap. Do not put expected output fields into the model context.

## 6. API/storage seams

- A owns intake/case/review/reanalysis/queues plus feedback and annotation endpoints listed in the plan.
- B's Grafana contact point calls `POST /internal/alerts/grafana`; A owns local authentication, size limits and persistence. A test receiver may be used for B's isolated webhook test.
- `GET /api/v1/operations` exposes persisted cost/anomaly/capacity/SLO/incident status; no model calls.
- Evaluation/drift runners submit records through A's agreed adapter or export versioned result files for explicit import. No direct writes to the live SQLite database.
- A exposes persisted evaluation/feedback/operations observations through B's instrumented API. Short-lived scripts do not need a Pushgateway or extra permanent service.
- Prometheus scrapes Collector-exported application metrics; Jaeger receives traces. Grafana alone evaluates notification rules. Local development logs are redacted; no log-storage stack is required.

## 7. Required common fixture vectors

1. Valid SEV3 classification -> safe personalized draft -> awaiting review; exactly two normal stage calls.
2. Fake classifier predicts SEV3 for a covered financial-harm complaint -> effective SEV1 -> drafting uses effective context -> urgent review; raw miss retained.
3. Valid SEV1 classification -> drafting timeout -> manual-required with saved classification, urgency and failed-attempt usage status; no route.
4. Rule finding plus negative feedback on one revision -> one pending annotation item, two reasons, no authoritative label.
5. Same Grafana firing webhook twice -> one incident episode; priority escalation is preserved; resolved update is processed.
6. SLO target 99%, 100 eligible outcomes, 2 bad -> burn rate 2, remaining bad allowance -1; unknowns excluded and coverage displayed.

Only the first three must exist in the initial bootstrap; B/C add the latter vectors without changing the frozen common shapes.

## 8. Proposed validation and integration rules

Common command after PR-0: `uv run pytest tests\contracts -q`. If shared types/configuration are absent, stop and request the merged foundation instead of inventing another scaffold.

All phases first test their functions with these fixtures. Live mode uses the configured provider, not fixture adapters, and has no application spending caps. Contract v1 agreement is not a substitute for runtime proof.

Each PR must pass its phase tests plus the full currently available suite and static checks on the final updated commit. Final wiring is a separate PR-I after all module PRs merge. Refer to Section 10.7 of the plan for exact per-PR gates; no CI/CD pipeline is required.
