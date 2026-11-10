# Person B - AgentOps, Module 6 and Module 7

Share this file with [the plan](plan.md), [shared contract v1](shared-contract-v1.md) and [README](README.md). The target starts as a NEW BLANK repository; no existing complaint application or host-repository tooling is assumed.

## Copy-ready Copilot task

Implement Phase B only. Read the plan and shared contract first; summarize owned surfaces, deterministic acceptance criteria and first failing test. Do not wait for live agents: replay agreed stage/completion fixtures.

### Blank-repository start and your separate PR

1. Supply required contracts/dependencies to A's foundation PR-0; it starts from the new repository's README-only anchor. Do not generate a competing scaffold, manifest, lockfile or shared types.
2. Wait for PR-0 to be tested/reviewed/merged, then create `feat/phase-b-agentops` from that `main` and open **PR-B** into `main`.
3. A/C implementation need not exist. Build pure operations and telemetry against the merged contract fixtures; do not import API, agents or evaluator modules that are not merged.
4. Your development runs in parallel with A/C. Merge order is **PR-0 -> PR-A -> PR-B -> PR-C -> PR-I**. Before PR-B merge, update your branch against `main` containing PR-A and rerun all gates.
5. While A is unfinished, run only the four observability backends and bounded fixture-signal/webhook tests. Do not claim that missing API/UI containers or an unavailable real inbox are fully integrated.
6. After PR-B merges, review/help A's separate PR-I for real stage instrumentation, capacity enforcement and alert-inbox wiring; do not bundle that wiring into PR-B.

If foundation files are absent, stop and request PR-0 rather than assuming a hidden application exists.

### Own

`telemetry.py`, `cost.py`, `model_policy.py`, `capacity.py`, `slo.py`, `incident_response.py`, `fixture_signals.py`; `observability\`, `compose.yaml`, operations/pricing config, runbooks, telemetry and phase-B tests.

Propose shared model-config/manifest changes to A; do not edit application state, prompts, labels, UI or migrations. B functions return typed records. A owns persistence and the alert inbox API.

### Module 6 slices - test first

1. Price reported tokens with explicit units/version; aggregate by stage/model/run mode. Unknown usage/pricing is incomplete, not zero. Replayed event IDs do not double-count.
2. Distinguish stage versus total workflow latency/cost; avoid counting parent and child cost twice.
3. Stage-based model policy: explicit classification/drafting model mapping and reason. No severity-based routing or silent fallback. Start with the approved mapping; propose a different mapping only with C's comparative evidence.
4. Frozen 15-sample cost baseline plus 8 eligible recent complete-analysis costs; warn at >=3x mean. Test warmup, zero baseline, missing usage, changed model-policy and normal variation.
5. Configurable two-workflow capacity helper with safe reserve/release and explicit overload result. A enforces HTTP behavior. Use blocked fake providers, not a paid load test.

### Module 7 slices - test first

1. Compute declared SLIs from good/bad/unknown outcomes and sample eligibility. Unknown quality is not good.
2. Validate error-budget maths: 99% target, N=100, B=2 -> burn 2 and remaining bad allowance -1. Handle no eligible samples and target 100% without divide-by-zero.
3. Separate complaint severity from P1/P2/P3 incident priority. Cost degradation is not automatically P1. Unknown rule mappings need visible review.
4. Adapt actual Grafana firing/resolved payloads to episode records. Duplicate delivery is idempotent; resolution and priority escalation remain visible; preserve affected case evidence.
5. Provide blameless postmortem export and actionable runbooks. No extra Python alert-rule engine: Grafana owns evaluation.

### Telemetry and local stack

- OTel Collector -> Jaeger for traces; Collector metric exporter -> Prometheus; Grafana queries both.
- Grafana built-in alerting calls A's local authenticated webhook/inbox.
- Default redaction excludes complaint/draft text, prompts, evidence snippets, keys and full exception bodies. IDs stay out of metric labels.
- Runtime exporter failure is visibly degraded, not a fake successful export.
- Use `fixture_signals.py` to generate explicitly fixture-tagged records. It must not import or call OpenAI.
- No Redis, response cache, standalone Alertmanager, Kubernetes, CI/CD or release controller.
- A owns API/UI services; provide Compose service definitions against the agreed entrypoints and keep the telemetry fixture path independently runnable.

### Proposed commands

```powershell
uv run pytest tests\contracts tests\test_telemetry.py tests\phase_b -q
docker compose config --quiet
uv run ruff check .
uv run mypy src
```

Validate Prometheus configuration and optional recording rules with the pinned container tools. Grafana-managed alerts require actual isolated-stack firing/resolved webhook tests; `promtool` alone does not validate them. Stop fixture receivers/helpers when tests finish.

Before PR-B merge, run `uv run pytest -q` and `uv run ruff format --check .` on the final branch updated with PR-A. Record the base/final commit, phase tests, full-suite/static results and fixture-versus-integrated evidence in your PR. Final end-to-end checks belong to PR-I; no provider credentials are needed for PR-B.

### Reference and adaptation

The plan pins the public reference repository commit and relevant source links. Reuse concepts, not unreviewed code or domain labels. Correct its percentage-point/error-budget ambiguity, avoid class-only incident suppression and do not bring in its normalized response cache.

### Stop and report

No live model or external notification calls; no production traffic or unbounded load. Do not change shared schemas or A/C modules to force integration.

Hand off your separate PR, exact tests/results, exporter/redaction evidence, metric dictionary, dashboards/rules/runbooks, cost/SLO fixture outputs, requested dependency changes, webhook examples, model-policy gates and known limitations. Fixture-replayed costs are not measured OpenAI spend. No direct module pushes to `main` or bypass of failed gates.
