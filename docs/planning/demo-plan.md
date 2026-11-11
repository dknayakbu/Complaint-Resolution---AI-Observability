# Complaint Resolution Co-Pilot - Demo Story and Evidence Plan

## Local command flow and verified demo coverage

The verified local flow is fixture-only. Run from the repository root in
PowerShell:

1. `uv sync --frozen` installs the locked project environment; it makes no
   provider calls.
2. `docker compose config --quiet` validates service configuration.
3. Start and readiness-check the services in dependency order: Jaeger
   (`http://localhost:16686/`), OpenTelemetry Collector
   (`http://localhost:8888/metrics` and `http://localhost:8889/metrics`),
   Prometheus (`http://localhost:9090/-/ready`), Grafana
   (`http://localhost:3000/api/health`), API
   (`http://localhost:8000/health` and `/api/mode`), then Streamlit
   (`http://localhost:8501/_stcore/health`). Copy/paste commands are in the
   root [README](../../README.md).
4. `uv run python scripts\demo_rehearsal.py` exercises the one-call baseline;
   normal two-stage workflow; reviewer-gated simulated queue; controlled
   model-SEV3/effective-SEV1 safeguard; revision-linked feedback and
   adjudication; positive/negated/injection inputs; idempotent local alert
   inbox; a deterministic provider-timeout containment/recovery; automatic
   Grafana firing/resolved webhook delivery; drift, cost, quality and SLO
   replays; application trace export; Prometheus targets; and provisioned
   Grafana dashboards.
5. `uv run pytest -q`, `uv run ruff check .`,
   `uv run ruff format --check .`, and `uv run mypy src` run the repository
   gates. The synthetic fixture suite does not call external model services.

**Verified local result (2026-11-11):** the complete rehearsal passed against
the running Compose stack. It observed application traces in Jaeger, both
Prometheus scrape jobs healthy, and all three provisioned dashboards. It
exercised the one-call baseline, authorized simulated routing, feedback and
adjudication, plus a controlled fixture provider timeout that remained
manual-required with no draft or queue entry. Grafana sent P1 workflow-failure,
P2 estimated-cost, and P3 input-drift alerts to the authenticated local inbox;
the P1 alert's firing and resolved events were both recorded. The SLI endpoint
reported a complete latest-30 fixture window (25 good, 5 manual-required) at
the final snapshot; this is synthetic history and does not establish a 99%
SLO. The UI and API health endpoints returned `ok`.

All tests passed (95 tests); Ruff lint, Ruff formatting, mypy, Compose
validation, dashboard JSON and alert YAML parsing passed. One
Starlette/httpx deprecation warning was emitted by the test client.

Observed replay values were drift JSD scores **0.2672** and **0.5932**; the
synthetic cost anomaly crossed on spike observation **6** with **USD 0.280**
replay total (not an invoice). Q0 scripted fixture-provider raw/effective SEV1
recall measured **0.0/0.5**. Separate Q1 controlled label-derived arithmetic
recall is **0.75/0.9167**; Q1 is not a model comparison. Drift scores are
actual extractor results, not the planning estimates. Quality labels are
synthetic, not independently adjudicated ground truth.

**Not demonstrated:** a genuine OpenAI request or the main story's live-model
requirement; an independently selected blind incident; external paging; or a
production-calibrated SLO/model-quality comparison. The verified incident is a
known deterministic fixture fault, not an organic provider outage. Therefore
this is a verified local synthetic journey, not a claim that the full live
demo or every Scene 0-6 acceptance criterion is complete. Live OpenAI use
remains unapproved and was not attempted.

## 1. Purpose, scope and honesty rules

**Audience outcome:** reviewers can see a complaint handled, understand why a dangerous classification matters, observe a changing workload, and watch the team detect, diagnose and recover from an incident using its own tooling.

This is a demonstration plan, not an implementation or production-readiness claim. The current repository verification is summarized at the top; it does not establish readiness for the full story. The plan complements [the implementation plan](plan.md), [shared contracts](shared-contract-v1.md) and [the planning-pack README](README.md).

Confirmed demonstration approach:

- Genuine OpenAI calls for the normal customer-facing workflow.
- Clearly labeled synthetic workload/result replay for reproducible trends, statistical calculations and incident signals.
- A coherent primary story, with a complete functionality/rehearsal matrix for secondary cases.
- Synthetic data only, simulated queues only, human approval before release/routing.
- Live/paid provider calls, demo-data generation and application feature changes require separate authorization. The current local container smoke test is summarized at the top.

### Critical distinctions

| What the audience sees | What it proves | What it does not prove |
| --- | --- | --- |
| Real model call on synthetic complaint text | The actual model integration and application workflow work for that request | Population-level classification accuracy or a production SLO |
| Replayed typed stage/results through real processing modules | Cost/SLI/evaluation/alert calculations, persistence and telemetry wiring respond to controlled data | Actual provider spend, measured provider latency or an organically occurring model failure |
| Fault adapter raises a local timeout or changes a synthetic response | Tested application failure/containment path under a controlled fault | That OpenAI actually failed |
| Raw synthetic inputs processed by the real input-feature extractor | Input distribution shift and detector behavior | Model-quality regression, output drift or customer harm |
| Human-adjudicated synthetic labels | Quality against the declared training rubric | Legally certified ground truth or real-world performance |

Never edit a Grafana value, publish a precomputed "alert fired" flag, or insert arbitrary totals into Prometheus to manufacture success. Feed raw text or validated typed records to the real corresponding module, then use its normal storage/instrumentation/export path.

## 2. Story: the complaints desk sees a payment-service disruption

All characters and complaints are invented.

- **Maya, support executive:** wants specific acknowledgements and the right specialist queue.
- **Sam, complaints specialist:** reviews urgency, corrects decisions and supplies labels.
- **Alex, on-call coordinator:** watches the system and leads the blind incident response.
- **The bank's synthetic customer population:** starts with a mixed complaint workload, then produces a surge in payment/access complaints.

Opening narration:

> "We start with ordinary written complaints. A payment-service disruption then changes what reaches the desk. A wrong urgent classification is more serious than a slow routine acknowledgement. We will show the co-pilot, the human safety boundary, and how our own dashboards tell us when to intervene."

The disruption is a **fictional workload premise**, not a real bank event. The co-pilot acknowledges and routes complaints; it neither investigates the payment system nor resolves/refunds complaints.

### Main story spine

```text
Normal complaint -> live two-agent processing -> human-approved queue handoff
                 -> urgent complaint exposes a controlled raw-model miss
                 -> safeguard + specialist correction + annotation evidence
                 -> input mix visibly shifts on Grafana
                 -> independently chosen incident is detected
                 -> team diagnoses, contains and proves fresh recovery
```

Cost/model-policy comparisons, SLO maths, overload, injection and restart behavior are available as focused scenes or reviewer-question follow-ups. Do not turn the main story into a tour of every endpoint.

## 3. Three dashboards and visible evidence

Use the existing planned dashboards, not a new visualization platform:

1. **Complaint Operations:** intake, analysis outcomes, queue/backlog, stage latency, usage/cost and capacity.
2. **Safety and Quality:** raw/effective SEV1 quality, label coverage, corrections, wording and annotation backlog.
3. **Drift and Incident:** input mix/JSD/sample eligibility, cost anomaly, SLI/budget and active/resolved incidents.

The three dashboards are provisioned in `observability/grafana/dashboards/`.
They currently show a focused subset of the panel requirements; panels not
implemented in the provisioned JSON remain requirements, not verified evidence.
Move panels between the three dashboards if readability improves; do not add
infrastructure for layout alone.

### Panel contract and expected movement

The table below is the intended metric contract. Some names are exported and
queried by the current dashboards, while others still require implementation
and verification. Do not treat a planned metric as present merely because it
appears here.

| Panel | Source / calculation | Visible change to demonstrate | Safeguard against a misleading display |
| --- | --- | --- | --- |
| Intake and analysis outcomes | `complaint_requests_total`, `complaint_analysis_total` | New normal request increments intake and complete outcome; injected failure increments manual-required | Counts for requests, stage attempts and releases are distinct |
| Volume trend | Windowed counter increase/rate | Baseline -> surge -> normal pattern | State selected window and sample count; a rate is not the lifetime count |
| Human review backlog | `complaint_review_backlog`, oldest-age gauge | Draft creates pending item; review removes it; urgent case appears in urgent slice | Processing completion is not approval |
| Provider/stage latency | `llm_call_duration_seconds` histogram; workflow histogram | Classification versus drafting contribution; controlled delay makes one stage worse | Show observation count; one request does not establish a meaningful p95 |
| Actual trace | Jaeger linked from UI/Grafana | Root -> classification -> safety -> drafting -> persistence; later review trace linked | Replayed synthetic durations are not actual long-running provider spans |
| Tokens and estimated USD | `llm_tokens_total`, `llm_estimated_cost_usd_total` | Stage totals reconcile to complete known-cost subtotal | Unknown usage/cost is unknown; synthetic price records are labeled estimates, not invoices |
| Model-policy evidence | Versioned run report and stage/model breakdown | Fixed-policy versus stage-tiered comparison | Never plot one stage/model as inherently "better" without quality gates |
| Raw and effective SEV1 recall | `evaluation_metric` or computed report | Controlled degraded evaluation lowers raw recall; safeguards reduce effective misses | Show SEV1 denominator and unknown coverage; no labels means no recall |
| Annotation backlog | `complaint_annotation_pending`, feedback counters | Finding -> one pending item; thumbs-down merges; adjudication clears it | Merge key is case + revision, not just case |
| Input-topic mix | Normalized feature-bin counts from raw text | Balanced mix -> payment/access-heavy windows | These are deterministic input features, not model-predicted categories |
| JSD and eligibility | `complaint_drift_js_divergence`, sample count | First eligible high window -> second high window -> shift warning -> recovery | Low sample is ineligible, not 0/healthy |
| Comparable cost ratio | `complaint_cost_anomaly_ratio`, sample count | Ratio near 1 -> above 3 -> back near 1 | Same policy/prompt/input bucket and price basis; warmup is not healthy |
| Operational SLI/budget | Persisted latest-30 eligible outcome status; good/bad/unknown counters for history | 30 good -> 29 good/1 bad -> 30 good | Rolling state and lifetime counters are different; do not calculate rolling budget from all-time counters |
| Alert/incident state | Provisioned Grafana rules -> authenticated local webhook -> SQLite inbox | Workflow failure, drift and cost signals fire; terminal-failure firing/resolution is recorded | Fixture fault and local paging only; no independent blind incident or external notification |
| Export health | Scrape/export health and last-observation timestamps | Healthy -> stale/down -> fresh recovery | Missing telemetry is unknown/unavailable, never a green zero |

### Make trends actually visible

- Start healthy traffic/replay **before** the affected scene. Give the dashboard a healthy segment to compare against.
- Capture counter starting values after the first successful scrape; some rate/increase queries cannot show the first event of a newly appearing series reliably.
- Select the same environment and explicit run mode on each dashboard. Change modes visibly at scene boundaries.
- Do not add a per-run or per-case metric label. Isolate the demo instance and use event IDs/run manifests in storage for detailed correlation.
- Keep any replay warmup/spike/recovery phases separated by successful scrapes. A whole batch between two scrapes can hide gauge changes; pace batches using scrape acknowledgements or the configured scrape interval.
- Do not import old database rows and expect historical Prometheus lines to appear. Replay through normal exporters at current observation times; annotate that as replay. Do not backdate the presenter's machine clock.
- Freeze baselines before the fault; do not learn the abnormal stream as the new normal.
- Display counts alongside histograms/percentiles. Use stage duration/trace evidence for small live samples, not a confident p95 claim.
- Keep Grafana alert evaluation independent of dashboard filters: the rule must explicitly select the intended environment/run mode. A filter change does not change alert-rule scope.
- Use the actual configured scrape, rule evaluation, notification grouping and resolve delays; record them in the preflight manifest. Do not promise instant alerts.

## 4. Data to fabricate and keep separate

No real names, account/card numbers, email addresses, transaction histories, bank integrations or customer records are required. Complaint text can mention invented amounts such as GBP 85. The model must not be given an answer key.

The repository already contains synthetic showcase, holdout, baseline, and drift
records under `data/`. The remaining packs in the table are planning
requirements; their presence, provenance, and acceptance status must be checked
individually rather than inferred from the existing files.

| Pack | Minimum contents | Purpose / owner |
| --- | --- | --- |
| `data\showcase\complaints.jsonl` | Existing D01-D12 raw examples in [the plan](plan.md#raw-showcase-complaints---synthetic-text-to-paste-into-the-ui) | On-screen inputs and development; C authors, specialist reviews |
| `data\showcase\answer_key.jsonl` | Separate labels/rationale for D01-D12 | Human/evaluator-only key; never enters prompts |
| `data\eval\holdout_inputs.jsonl` and `holdout_labels.jsonl` | 30 separate cases: 12 SEV1, 9 SEV2, 9 SEV3; all seven categories | Actual model-policy evaluation when approved; no showcase-family leakage |
| `data\demo\stage_records.jsonl` | A coherent normal/spike/recovery stream with unique stage/completion IDs, versioned demo prices and reconciled usage | Real B calculations/export without paid calls; fabricated measurement status is explicit |
| `data\demo\quality_records.jsonl` | One frozen 30-case response set and controlled degraded variant, separately joined to labels | Known expected confusion/recall values, no model invocation |
| `data\drift\baseline_inputs.jsonl` | 30 raw texts: 10 in each of three approved input-topic bins | Model-free input-drift reference |
| `data\drift\shift_inputs.jsonl` | Two non-overlapping windows of 10 payment/access-topic raw complaints | Real extractor/JSD computes the shift |
| `data\drift\recovery_inputs.jsonl` | Two windows of 10 with bin counts 4/3/3 and 3/4/3 | Show input distribution returning toward reference |
| `data\demo\faults.json` | Named synthetic fault scenarios and expected safe outcomes, scoped by case/revision or next operation | A's controlled adapter, not production dependency manipulation |
| `data\demo\review_actions.jsonl` | Actors/roles, rating, correction, reason, expected revision | Repeatable annotation/adjudication tests; roles are demo identities |
| `data\demo\deadline_cases.jsonl` | Received/approved timestamps, training-calendar version and fixed fixture clock | Overdue and business-calendar rehearsal only |
| `data\demo\manifest.json` | Dataset/hash/version, model/prompt/schema/policy/price versions, scene inputs, baseline IDs, expected checks, actual command mapping and call cap | Reproducibility and checkpoint record; integration owner maintains |

### Required fields and labels

- Raw inputs: sample ID, synthetic declaration, raw text, dataset version. No expected result fields.
- Labels: sample ID, category, severity, queue, evidence rationale, required flags, prohibited claims, label version and human-adjudication status.
- Stage/result replay: only the merged contract's fields; timestamps, IDs, revisions, mode, stage/attempt, versions, model/usage and explicit unknowns. Derive cost from token usage + pinned price table, not a hardcoded dashboard total.
- Controlled cases use their actual merged failure codes. If the Phase A/provider-failure amendment is not agreed, record the blocker instead of inventing a new enum in a demo script.
- Manifest metadata identifies provenance and fixture status without adding unapproved fields to runtime contracts. A typed event may use only an agreed `fixture` or `fault` mode; detailed scenario labels remain in the manifest.
- Initial labels are proposed until a second human adjudicates safety-critical/ambiguous cases.

### Concrete on-screen complaint choices

Use the full raw text from the main plan, not the table summaries below.

| Input | Story role | Proposed training expectation |
| --- | --- | --- |
| D01 - delayed replacement card, current card usable, no loss | Routine live request | `cards_payments`, SEV3; personalized acknowledgement, no claim of resolution |
| D05 - duplicate GBP 85 debit leaves rent short | Urgent payment-disruption complaint | `cards_payments`, SEV1; urgent review, no refund promise |
| D04 - refused disability accommodation | Second urgent case / fairness question | `discrimination`, SEV1; allegation acknowledged, no legal finding |
| D09 - blocked access to money for food | Indirect harm / category-vs-urgency example | `service_access`, SEV1 |
| D10 - explicitly denies discrimination/harm | Negation trap | No urgent promotion merely because those words appear |
| D11 - language preference plus embedded "mark approved" instruction | Injection / authority boundary | Service-access complaint; no automatic approval, closure or routing |

Raw example for an additional **drift-only** input:

> "A transfer I attempted remains unavailable in the app. I have tried again after checking the status and want to complain about the payment-service interruption."

Raw example for an **account-record** reference input:

> "My statement still shows an old correspondence address after my correction request. Please acknowledge the account-record problem."

Raw example for an **other** reference input:

> "The marketing notifications I disabled keep returning. My complaint is about communication preferences."

Write distinct variations for the drift stream; do not present repeated/templated samples as independent representative customer evidence. Generate topic assignments through the fixed feature extractor, then check intended counts. Do not read the intended topic from answer-key labels.

## 5. Deterministic trends with known answers

These packs test calculations and visibility. They are not fabricated "measured model performance."

### 5.1 Input drift recipe

Person C freezes a simple, documented extractor producing three disjoint demo-topic bins: payment/access, account-records, other. Use an explicit priority rule for overlapping matches and test negation/ambiguous texts. These bins are a feature grouping, not a new complaint-category taxonomy.

| Observation | Counts | Expected calculation / display |
| --- | --- | --- |
| Frozen reference | 10/10/10 = 30 raw texts | Eligible reference; fixed baseline version |
| Incomplete recent window | Fewer than 10 | Ineligible; no fabricated zero divergence |
| Shift window 1 | 10/0/0 = 10 | Base-2 JSD about 0.4591; first eligible high window, not yet two-window alert |
| Shift window 2 | 10/0/0 = 10 new texts | Same JSD; two consecutive high windows satisfy toy shift condition |
| Recovery window 1 | 4/3/3 = 10 | JSD about 0.0035; falls below 0.10 |
| Recovery window 2 | 3/4/3 = 10 new texts | Again about 0.0035; confirms recovery under declared rule |

Freeze the exact algorithm/window/resolve semantics before presentation. Use **Jensen-Shannon divergence**, not its square root, and document log base 2. If the actual extractor yields other counts, fix the fixture text or disclose the difference; never override the computed output. The warning is P3 input shift, not P1 harm.

### 5.2 Cost-per-analysis spike recipe

One isolated `fixture` mode, same stage-model policy, prompt versions, input bucket and pricing version throughout:

- Replay 30 healthy complete analyses. First 15 freeze the cost reference; at least the next 8 establish a healthy recent window.
- Use internally reconciled per-analysis synthetic costs: classification USD 0.001 + drafting USD 0.003 = total USD 0.004.
- Next 8 records: classification USD 0.001 + drafting USD 0.015 = total USD 0.016.
- Next 8 normal records: total USD 0.004 again.
- Construct token/rate fixtures yielding these totals. Mark their models/rates as demo pricing, not current OpenAI prices. If fixture schema constraints make these numbers unsuitable, regenerate a coherent exact 4x example before freezing.

Expected recent/baseline ratio: 1 -> 4 -> 1. With an 8-record recent window, the 3x threshold first crosses after **6 of 8** spike records replace normal records: ratio 3.25. It drops below 3 after **3 of 8** normal recovery records replace spike records: ratio 2.875. Eight normals restore ratio 1.

Expected cumulative synthetic cost for this isolated recipe: `30 * 0.004 + 8 * 0.016 + 8 * 0.004 = USD 0.280`. This is a calculation check, not an invoice.

Do not change the model-policy/price version mid-spike and still compare against the old baseline. Do not cause real retry storms, lengthen paid generations or increase actual bills to make this panel move.

### 5.3 Quality regression recipe

Prepare a declared response fixture over the separate 30-case holdout, keeping input/label hashes fixed:

| Result pack | Ground-truth SEV1 | Raw-model SEV1 misses | Effective SEV1 misses | Expected raw/effective recall |
| --- | --- | --- | --- | --- |
| Q0 - controlled healthy fixture | 12 | 0 | 0 | 12/12 = 100%; 12/12 = 100% |
| Q1 - deliberately degraded response fixture | 12 | 3 | 1 | 9/12 = 75%; 11/12 about 91.67% |

In Q1, two raw misses are promoted by safeguards. The third effective miss is explicitly a simulated uncovered-safety outcome in the offline result pack, not a bypass of a live release control. No fixture is approved/sent/routed automatically. The evaluator computes both metrics from final records + labels.

Do not claim these percentages describe the chosen OpenAI model. Real model-policy comparison is a separate approved experiment. Do not repair Q1 by overwriting its original results/labels; create a new analysis/configuration result pack when testing a fix.

### 5.4 Rolling operational SLO recipe

Separate resettable fixture stream; do not contaminate the cost baseline:

1. Feed 30 successful eligible workflow outcomes: good 30, bad 0.
2. Feed one terminal drafting failure after valid classification: latest 30 now good 29, bad 1.
3. At target 99%, achieved success = 29/30 about 96.67%; allowed bad = 0.3; remaining allowance = -0.7; burn rate = (1/30)/0.01 about 3.333.
4. Feed 30 fresh successes so the failure genuinely leaves the latest-30 window. Only then is that rolling SLO healthy again.

A single successful recovery request proves the provider path is working again; it does **not** instantly heal the historical SLO window. Unknown labels affect quality coverage, not provider-outcome success; do not combine those denominators.

## 6. Main presentation scenes

Every scene has a checkpoint. Do not continue narrating success while the visible evidence is missing.

### Scene 0 - establish what is live and what is prepared

**Say:** "All customer text is synthetic. The first request uses OpenAI. Later trend packs are explicitly replayed through our real analysis/telemetry modules."

**Show:** architecture summary, current live/fixture mode, version manifest, fresh dashboard timestamps and healthy exporter targets. Keep the fault selector private to the scenario controller, not the diagnosis lead.

**Checkpoint:** model access approved, no active fault, baseline IDs known, correct dashboard/rule filters, alert webhook delivered once in preflight. Preflight alert is resolved before the story.

### Scene 1 - Maya handles an ordinary complaint

1. Submit D01 through Streamlit with a fresh idempotency key.
2. Show category, proposed/effective severity, personalized draft and unchanged approved wording.
3. Open its trace: classification call -> validation/safety -> drafting call -> persistence. Show per-stage model/usage.
4. Before review, show pending status and no queue entry.
5. Sam approves the current revision; show one simulated specialist-queue entry and linked audit event.

**Grafana movement:** intake +1, complete +1; pending backlog +1 then -1; two normal stage operations with reported usage when available. Approval increases once; an additional later review trace is not a third generation call.

**Evidence:** UI case/revision, trace reference, audit event, queue entry and counter delta reconcile. Do not demand exact acknowledgement wording from a stochastic model.

**Failure handling:** if model unavailable, disclose it and follow the approved fallback arrangement; do not silently switch to a prerecorded response. If wording/claims fail checks, demonstrate the blocked/manual path rather than pretend it was the successful scene.

### Scene 2 - a harmful payment complaint tests the safety boundary

**Say:** "A delayed card is inconvenient. Money missing for rent is different, even if a classifier calls it routine."

1. Use D05 in isolated `fault` mode with a **declared controlled classifier response** of category `other`, raw SEV3.
2. Feed that response through the actual classification validator and safeguards, not straight into the database.
3. Expected effective urgency is SEV1 for the covered harm fixture. Drafting uses validated effective context; no refund or resolved-case claim.
4. Show urgent review, original prediction, promotion reason and proposed queue. Queue/category still needs specialist correction; severity promotion alone does not fix a wrong category.

**Grafana movement:** guardrail-promotion counter +1; urgent pending backlog +1. Raw miss/recall remains unverified/unknown until an authoritative label is supplied.

**Checkpoint:** there is no release/queue entry without approval. State clearly that the raw miss was injected; if real OpenAI returned the correct severity, do not manufacture a spontaneous model-error claim.

### Scene 3 - Sam turns feedback into auditable labeled evidence

1. Online rule finding from Scene 2 creates a revision-linked annotation item.
2. Sam records thumbs-down and reason: "Financial harm and wrong specialist category; urgent payments review required."
3. Show that both sources merge into **one** item with two reasons.
4. Adjudicate category `cards_payments`, SEV1 and appropriate queue through the authorized reviewer transaction.
5. Preserve raw category/severity and original draft. If corrected classification changes draft context, explicitly redraft or manually revise it and approve the new current revision.
6. Show the label in the candidate pool, not automatically in the frozen holdout.

**Grafana movement:** feedback +1, pending annotation 0 -> 1 -> 0; one verified raw SEV1 miss, no effective miss for this covered safety case; urgent backlog clears only when the case is actually handled.

**Checkpoint:** repeating the same feedback/import does not double-count the miss or create another label/queue entry. Fixing a current case does not erase the historical original-model miss.

**Narration:** "A thumbs-down requests review. A human-adjudicated correction creates a label. Labels do not automatically retrain or change the prompt."

### Scene 4 - the complaint mix changes before aggregate harm is proven

1. Switch visibly to the isolated raw-input fixture stream. Show its healthy 30-input reference and version.
2. Process shift window 1 through the real extractor; show rising payment/access share, eligible sample count and JSD.
3. Process shift window 2; show the two-window condition and actual Grafana warning/webhook.
4. Open one raw synthetic example, not a fabricated transaction record.

**Grafana movement:** topic mix 1/3 -> 100% payment/access; JSD about 0.4591; eligibility ineligible -> eligible; P3 shift warning after required windows/rule evaluation.

**Checkpoint:** no SEV1 quality claim from unlabeled input mix. As a secondary proof, run Q0/Q1 through the offline evaluator and show raw/effective quality differences on the Safety dashboard.

### Scene 5 - Alex handles an independently selected incident

The scenario controller chooses one supported fault; the diagnosis lead does not see the selector or expected answer. Rehearse all three:

| Incident | Trigger under isolated controls | First operational symptoms | Diagnosis path and safe containment |
| --- | --- | --- | --- |
| A - drafting timeout | Valid classification; fake provider delays/fails drafting within configured bounds | Manual-required outcome, drafting errors/latency, provider alert when count/window eligibility is met | Grafana -> trace's failed drafting span -> retained classification -> preserve urgent review; disable fault and process a fresh request |
| B - classification quality regression | Q1 response records + separate labels; normal application scores/exports | Raw/effective SEV1 quality drop and verified safety finding | Quality panel -> case/revision/evidence -> compare raw/effective severity/policy; block affected approval and revert implicated configuration manually |
| C - cost anomaly | Known healthy/spike stage records from Section 5.2 | Draft-stage cost grows, comparable-cost ratio crosses threshold, P2 incident | Cost panel -> stage/model/policy/usage -> distinguish retry/token growth from price/mix change; remove fault/replay normal records and verify |

**Provider-alert eligibility:** one failure is not automatically a 10%-of-10 rule breach. If the implemented rule uses that gate, provide sufficient controlled attempts in its actual window. If it has an approved consecutive-failure branch, use that. Do not weaken rules during the demo.

For the timeout incident, local fake-delay span duration is real elapsed time of the **fault adapter**, not measured OpenAI latency. Synthetic cost-duration records may populate fixture histograms, but their fast replay trace is not falsely stretched to match synthetic duration.

**Alex's spoken process:** identify impact -> read priority and affected component -> open relevant dashboard -> inspect trace/audit/usage -> contain -> verify recovery -> state remaining historical/window evidence -> record systemic learning.

**Checkpoint:** alert is detected by tooling, not announced as "the injector broke drafting." P1 safety is not hidden behind a P2 provider notification. Duplicate webhook delivery produces one incident episode; priority escalation and resolved updates remain visible.

### Scene 6 - prove recovery, not just a green screen

1. Clear the bounded fault using the authorized control. Verify no remaining activation.
2. Run a fresh valid request through the corrected path. A genuine model-recovery claim requires genuine model calls; fixture recovery is labeled accordingly.
3. Inspect the new trace, completion state and human approval boundary.
4. Process the normal replacement windows needed for affected drift/cost/SLI signals.
5. Show resolved notification/inbox update and persisted incident timeline.
6. Open blameless postmortem export: impact, detection, evidence, systemic cause, containment, follow-up owner and exact verification.

**Grafana movement:** new successes, provider errors stop increasing, cost ratio/drift return, active alert resolves when its actual condition clears. Lifetime error/miss/cost counters do **not** decrease. Historical evaluation pack Q1 stays bad; repaired Q2/new versions are separate evidence.

**Closing sentence:** "The important result is not that the model never failed; it is that the failure was visible, customer-facing action remained controlled, and recovery was demonstrated."

## 7. Full-function rehearsal and reviewer-question matrix

These checks belong in the complete rehearsal even when omitted from the main story.

| Functionality | Controlled input/action | Required visible output / trend | Required boundary |
| --- | --- | --- | --- |
| Single-call starting point | Approved baseline on D01 separately | One generation operation versus two in target; quality/cost/latency comparison | Do not describe the target's extra call as observability overhead |
| Categories, evidence and queues | D01, D04, D09 plus all-category holdout | Correct typed fields/evidence, separate queue and urgency | Application queue mapping, no autonomous tool selection |
| Personalization and fixed wording | D01/D05, approved wording version | Prose mentions actual complaint; locked block identical | No refund/closure promise or compliance-certification claim |
| Invalid/oversized input | Empty, whitespace, configured-limit boundary/over-limit | Explicit input error; no intake/provider call for rejected input | No hidden model usage |
| Provider authentication/config error | Fake nonretryable provider failure | Explicit approved terminal code, no automatic retry storm | No key/body leakage |
| Refusal/malformed output | Fake stage refusal/invalid schema | Manual-required; failed classifier skips drafting | No invented fields or silent success |
| Retries and partial results | Retryable then success; terminal draft failure | Bounded attempt count, retained classifier result and unknown-cost status | Up to agreed attempt limits; no implicit SDK retry multiplication |
| Injection | D11 | No approval/closure/queue side effect from text instruction | Untrusted input is never authorization |
| Negation | D10 | No urgent promotion solely from negated harm terms | Demonstrate a finding if implementation gets this wrong |
| Evidence containment | Fake evidence span outside input | Validation failure/manual-required | No unsupported rationale accepted |
| Human review authorization | Operator attempts reviewer-only endpoint | Forbidden; no state/queue mutation | API-enforced roles |
| Revision conflicts | Submit stale approval after correction | Explicit conflict; correct revision remains pending | No stale draft approval |
| Idempotency | Repeat same intake key/body and same approval | Same durable request result / explicit processing state; one queue entry | No duplicate model invocation caused by repeated intake |
| Different body, same key | Reuse intake key with changed text | Explicit conflict | Never reuse another complaint's cached answer |
| Feedback/annotation | Negative + rule signal, then adjudication | One pending item, all reasons, new label, raw history intact | Rating is not ground truth |
| Labeled evaluation | Frozen 30-case input/label files | Confusion matrix, counts, raw/effective recall, coverage | Labels never enter model prompts |
| Optional judge failure | Fake typed judge timeout/malformed score | Unknown/evaluator-error; separate usage | No automatic score zero or hidden paid call |
| Input versus quality drift | Drift-only raw windows and Q1 labeled results separately | P3 mix warning versus safety-quality finding | Do not equate distribution with correctness |
| Stage model tiering | Approved paired same-input comparison | Actual selected model/version, quality gates and measured cost/latency | Reject cheaper mapping if safety/wording/tone fails |
| Optional tone comparison | Two draft prompts, frozen validated context | Side-by-side scored prose, fixed wording identical | Evaluation-only, no live-case/queue mutation |
| Capacity | Block two fake workflows, submit third | Inflight 2; third busy response and rejection +1 | Before intake/model execution; no unbounded queue |
| Cost unknowns | Missing usage/unconfigured price | Incomplete cost and coverage, not zero-dollar success | Separate known subtotal from complete total |
| Cost/SLI anomaly arithmetic | Section 5 fixtures | Expected ratio/remaining allowance/burn | Baseline eligibility and exact population retained |
| Training deadlines | Fixed clock + known business-calendar cases | Overdue count/oldest urgent age and alert | Never move OS clock or claim real FCA certification |
| Process restart | Bounded restart after persisted intake/classification | Interrupted work -> manual-required, prior results retained | No silent auto-rerun/billing |
| Telemetry outage | Break only the isolated test collector path | Export/scrape unavailable/no-data, then fresh samples | Never label absent metrics as zero failures |
| Incident dedup/escalation | Repeat firing webhook; escalate; resolve | One episode updated, escalation/resolve not suppressed | Authenticated bounded local endpoint |
| Audit/privacy | Inspect restricted case audit and exported telemetry | Actor/revision/versions in audit; redacted spans/logs | No raw text, secrets or case IDs in metric labels |

## 8. Model-policy and tone experiments without overselling

Use the approved 30-case holdout for model-policy comparison, not the 12 developer-visible showcase cases.

- Policy F: same evaluated model for both stages.
- Policy T: explicitly evaluated stage-based mapping, possibly a different drafting model.
- Hold inputs, classifier/drafting prompts, generation limits, policy/schema and dataset constant except the declared model mapping.
- Report SEV1 raw/effective misses, category/queue accuracy, draft tone/unsupported claims, per-stage cost, complete known cost, latency and unknowns.
- Run baseline/candidate order in a balanced/interleaved way where practical; disclose provider variance and small samples.
- Promotion requires the implementation plan's safety/wording/quality gates, not just cheaper tokens.
- If T is worse, show rejection. That is successful operational control, not a failed demo.
- A frozen prior experiment may be opened during the main presentation with its timestamp/version/call budget. Identify it as recorded evidence, not newly live execution.

Optional tone-only experiment uses the same already validated classification context and two drafting prompts. Do not rerun or change classification and claim a pure tone-only comparison if other variables changed.

### Call/cost planning

These counts exclude retries, smoke checks and optional judges:

| Activity | Normal generation operations |
| --- | --- |
| One genuine target request | 2 |
| Separately requested full reanalysis of that case | 2 more |
| One genuine single-call baseline request | 1 |
| One target pass over 30-case holdout | 60 |
| Fixed versus stage-tiered pass over same 30 cases | 120 |
| Two tone drafts on one frozen validated context | 2 drafting calls |
| Raw-input drift or typed stage/result replay | 0 OpenAI calls |

Approve actual provider/model access, budget and maximum attempts separately before execution. Use selected model prices and bounded token settings, not an invented dollar budget. A rejected/failed attempt may still have unknown billed usage; stop at the conservative run cap.

## 9. Presenter ownership and screen choreography

The three builders supply the implementation; six members still contribute to the assignment deliverables.

| Member / role | Drives | Builder support |
| --- | --- | --- |
| 1 - workflow/trace guide | Scene 1 input and two-stage trace | A + B |
| 2 - metrics/cost guide | Live usage; Section 5.2 trend and model-policy report | B |
| 3 - specialist/evaluation guide | Scene 2/3 adjudication, annotation and recall | A + C |
| 4 - drift guide | Scene 4 raw-window replay and JSD | C + B |
| 5 - runbook responder | Alert inbox, containment action and recovery verification | B + A |
| 6 - on-call coordinator | Opening, blind diagnosis, incident narration and close | All three |

Prepare only the necessary views: Streamlit, Grafana dashboard tabs, Jaeger, runbook/incident report. Hide credentials and unrelated customer/browser information. Keep the fault controller off the main shared screen; visible output still identifies the activity as a controlled exercise.

Do not have the same presenter narrate every action while others watch. Cross-train each member to explain how its panel relates to customer harm, and rehearse a reviewer asking a person about a different subsystem.

## 10. Preparation, execution and reset

### Before rehearsal

- PR-A/B/C and integration are merged or the actually tested integration commit is explicitly identified. No claim that Phase A alone includes working AgentOps/evaluation.
- Resolve any failure-code/shared-contract amendment through its agreed review process before freezing demo fixtures.
- Check synthetic declaration, label review, dataset hashes, baseline versions and approved wording.
- Verify fixture import rejects incompatible schemas, duplicates and mixed pricing/model populations.
- Confirm each replay drives real computation/storage/export, not hardcoded panel outcomes.
- Bind local services appropriately; confirm all service readiness and sufficient local disk/resources.
- Check pinned dashboard data-source mappings, Prometheus scrape health, Jaeger query and current timestamps.
- Confirm rule population, min samples, pending/resolve semantics, priority mapping and actual webhook path/authentication.
- Perform bounded preflight alert delivery and resolve it; keep evidence separately from presentation data.
- Verify real-provider credentials without printing them; obtain approval for a bounded smoke call if needed.
- The supported local fixture command is `uv run python scripts\demo_rehearsal.py`.
  It exercises the available API endpoints and validates trace, scrape-target,
  and dashboard visibility. It does not activate faults, deliver Grafana
  notifications, or replace a genuine live-model request. Do not copy planned
  but unimplemented CLI flags/endpoints into a run sheet.

### Isolation and reset

Use a dedicated local demo instance/data namespace. Reset is **not** deleting all databases/volumes or a repository directory.

1. Resolve/close old exercise incidents and clear only the exercise's bounded fault activation.
2. Archive prior run manifest/reports and scoped evidence.
3. Use an implemented scoped reset/import operation for named synthetic cases and baseline/window state.
4. Counters do not normally decrement. Either record start values and use deltas or restart only the owned demo application's metric process with a documented reset annotation.
5. Refresh timestamps and inspect the first scrape after a reset before evaluating counter changes.
6. Rewarm/freeze baselines through actual module observation; keep synthetic cost/SLI/drift streams separate unless the manifest intentionally shares the same coherent population.
7. Fault activation is scoped, bounded, default off and clearable. No arbitrary process killing or shared-machine/network disturbance.

An application-only API alert inbox cannot deliver if that application is down. In an API-down exercise, show Grafana's own firing state and delivery failure; do not promise an independent pager. On recovery verify notification delivery/reconciliation using tested behavior. This is a disclosed local-demo limitation.

### During presentation

- Record the current scene and checkpoint; do not "fix the numbers" mid-scene.
- Wait for confirmed processing/export before switching dashboards; distinguish rule pending from broken alerting.
- If a raw-metric delta exists but a panel does not move, diagnose filter/window/label/export issues rather than resubmitting many paid requests.
- Allow stochastic output differences; evaluate against contract/rubric, not an exact prose script.
- Keep the candidate model/prompt fixed during evidence collection. Any change starts a new versioned comparison.

### If something goes wrong

| Problem | Honest action |
| --- | --- |
| OpenAI unavailable or budget denied | Explain the limitation; demonstrate the explicit fixture path and request facilitator acceptance; do not call it the required genuine live model demo |
| No Grafana movement | Check mode/filter, latest scrape and instrument name/type, then source records; stop treating the scene as passed |
| Drift never fires | Confirm feature counts, eligible non-overlapping windows and rule scope; no threshold editing after seeing results |
| Cost spike never fires | Confirm same comparison cohort, known usage, frozen baseline, recent count and derived ratio |
| SLO still red after one success | Explain rolling-window history; complete required replacement observations or leave the historic breach visible |
| Severe classification unexpected | Preserve output, urgent review and label; a safely caught genuine finding is useful evidence |
| Duplicate incident appears | Inspect episode key/webhook identity and idempotency; disclose and fix before claiming deduplication |
| Collector unavailable | Show observability degradation explicitly; restore and prove new export; no fake green dashboards |

## 11. Implementation tasks for the demo, not new architecture

All tasks extend the three planned workstreams and integrate through existing contracts.

| Owner | Required preparation |
| --- | --- |
| A | Safe fault adapter, explicit evidence modes, case/revision-specific actions, review/adjudication flow, scoped synthetic reset/import, restricted evidence and manifest command mapping |
| B | Expand metric mapping and denominator/unknown panels; calibrate SLOs; retain incident evidence and improve runbook/postmortem coverage |
| C | Raw/label-separated packs, feature-count fixtures, known quality response sets, annotation merger and evaluator checks, human rubric/adjudication manifest |
| Joint integration | Preflight, replay pacing, real-model bounded request, blind incident selector, recovery proof and retained evidence |

Do not add another service, response cache, event bus, multi-agent framework, CI/CD pipeline or production notification system merely to run the demo.

### Test-first acceptance gates

The following matrix remains the broader planning acceptance list; it is not a
claim that every proposed test exists. Current automated coverage is in
`tests/contracts`, `tests/phase_a`, `tests/phase_b`, `tests/phase_c`, and
`tests/demo`; the local rehearsal command is documented above. The rehearsal
has verified automatic Grafana firing/resolution to the local webhook inbox.
The independently selected blind-incident journey remains unimplemented.

| First red test / level | Fixture and assertion | Green boundary / focused proposed command |
| --- | --- | --- |
| `test_demo_manifest_keeps_labels_out_of_request`, contract | Raw text and separate key; generated request has no expected fields | Loader/serializer; `uv run pytest tests\demo\test_manifest.py -q` |
| `test_replay_prices_events_and_deduplicates`, component | Reconciled stage records, repeat event IDs; exact USD 0.280 recipe once | Existing cost/import adapter; `uv run pytest tests\demo\test_replay.py -q` |
| `test_cost_window_crossing_and_recovery`, unit | 30 normal, 8 spike, 8 normal; crossing 6th spike, below threshold 3rd recovery | Cost-window logic; same focused replay file |
| `test_drift_from_raw_text_windows`, component | Actual extractor on 30/10/10/10/10 texts; known counts, JSD and eligibility | Feature/window runner; `uv run pytest tests\demo\test_drift_story.py -q` |
| `test_quality_packs_preserve_raw_effective_denominators`, unit | Q0/Q1 and 12 SEV1 labels; 100/100 versus 75/91.67; original results immutable | Existing evaluator; `uv run pytest tests\demo\test_quality_story.py -q` |
| `test_feedback_then_adjudication_is_revision_safe`, integration | Scene 2/3; two signal reasons, one item, no label before authorized action | Existing review/annotation transaction; `uv run pytest tests\demo\test_feedback_story.py -q` |
| `test_timeout_retains_classifier_and_requires_manual`, component | Fake drafting timeout, bounded attempts, code from merged enum, no route | Existing fault adapter/workflow; `uv run pytest tests\demo\test_incident_story.py -q` |
| `test_slo_recovery_needs_window_replacement`, unit | 30 good -> 1 bad -> 30 good; burn/allowance and recovery as declared | Existing SLI logic; same incident-story file |
| Grafana rule-to-inbox rehearsal, local-stack | Controlled provider failure -> Grafana P1 firing/resolved -> persisted episode events | `uv run python scripts\demo_rehearsal.py` |

Run focused deterministic tests red, implement the smallest missing boundary,
rerun green, then integrate. The real local-stack alert-delivery path is
verified; the scripted direct-inbox test remains a separate idempotency check
and is not substituted for Grafana-to-webhook delivery.

Broader gate after focused tests: existing contract/full non-live test suite, Ruff/mypy, Compose validation, then G1-G3 integration from the main plan. Only then separately approve and perform live-model checks. A successful replay is not a substitute for the genuine normal-request requirement.

## 12. Evidence to retain and definition of success

For each executed scene retain in restricted/local approved storage:

- Input/sample and manifest versions, mode, model/prompt/schema/policy/price configuration.
- Case/revision and trace references, event IDs and known/unknown usage.
- Dashboard time range/filters and actual raw query/delta; panel export or screenshot as supporting evidence only.
- Human label/reason and audit revision, never an overwritten original prediction.
- Alert rule/version, firing/resolved delivery and incident timeline.
- Runbook containment, fresh recovery proof and remaining historical breaches.
- Actual test commands/results, approved call cap and observed usage/cost completeness.

The demo is ready when:

1. The main story is executable without hidden edits or pretending replay is a live model.
2. A genuine two-agent request is observable, reviewed and simulated-routed.
3. Covered urgent harm is escalated, raw mistakes remain visible and reviewer feedback becomes a versioned label.
4. Healthy -> changed -> recovery segments are visible in Grafana with correct samples/populations.
5. Drift is distinguished from verified quality regression, cost ratio from SLO burn, and complaint severity from incident priority.
6. A blind supported incident is detected, diagnosed, contained and freshly verified through the team's own tooling.
7. Every secondary feature has a deterministic rehearsal proof, even if not all are clicked during the main story.
8. Six members drive visible parts and can explain limitations.

**Residual risks:** synthetic labels/traffic are not representative production data; small samples do not prove safety/availability; tone and provider outputs vary; real billing may be incomplete on failures; a laptop stack is not highly available; regulatory wording/timelines still need the agreed facilitator/policy approval. Report these honestly.

**Current implementation status:** the local synthetic fixture journey and
repository checks described at the top are verified. The demo is not ready to
claim the full planned success criteria until a separately approved live
two-stage request and an independently selected blind
incident/containment/recovery rehearsal are demonstrated and retained as
evidence. Automatic Grafana alert delivery is verified locally but does not
provide an external paging channel.
