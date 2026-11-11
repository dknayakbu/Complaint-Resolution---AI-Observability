# Person A - Complaint Workflow and UI

Share this file with [the plan](plan.md), [shared contract v1](shared-contract-v1.md) and [README](README.md). Start from a NEW BLANK target repository, not the unrelated repository holding this documentation pack.

## Copy-ready Copilot task

Implement Phase A only: a Python 3.12+ FastAPI/Streamlit complaint co-pilot. Read the plan and shared contract first. Summarize scope, owned files, shared prerequisites, acceptance criteria and the first intended failing test before coding.

### Boundaries

- Maintain the approved single-call reference separately.
- Target Agent layer: internal Python orchestrator -> Classification Agent -> classification checks/SEV1 promotion -> Acknowledgement Drafting Agent -> draft checks/fixed wording -> saved draft -> mandatory human review -> simulated queue.
- Exactly two logical generation operations on the normal target path; no third planner, investigation agent, tools, auto-resolution, response cache or traffic canary.
- Use B's evaluated stage model policy through an injected interface, initially a recording/fixed fixture adapter. Never select a cheaper classifier from model-proposed severity.
- Only synthetic text; no customer communications or bank integrations. Fixed wording and taxonomy need facilitator approval before a live compliance claim.

### Blank-repository start and separate PRs

1. If the new remote has no commits, initialize `main` with a minimal README anchor so it can be a PR base. There is no existing application to inspect or reuse.
2. Open **PR-0**, branch `chore/foundation`, with only package/test configuration, lockfile, shared types, three contract fixtures and this planning pack under `docs\planning\`. Include B/C's agreed dependency needs. Do not implement workflow/UI/telemetry in PR-0.
3. Run foundation contract/static checks and obtain B/C review; merge PR-0 first.
4. From the merged foundation create `feat/phase-a-workflow` and open **PR-A** into `main`. This is a separate PR from PR-0.
5. Implement A against injected B/C fixture adapters. Do not import modules that exist only in unmerged branches.
6. PR-A is the first module PR tested/merged. B/C develop in parallel; the prescribed order is PR-0 -> PR-A -> PR-B -> PR-C -> PR-I.
7. After all module PRs merge, create a NEW `feat/integration-demo` branch and **PR-I** to wire real modules and verify joint behavior. Do not hide integration changes in PR-A.

If PR-0 already exists, use its merged types/configuration; do not create another root manifest or duplicate contracts.

### Own

`baseline.py`, `orchestrator.py`, `classification.py`, `acknowledgement.py`, `provider.py`, `policy.py`, `service.py`, `repository.py`, `api.py`, `ui.py`, `demo_controls.py`, application `Dockerfile`; API/review/state tests.

Merge approved shared contract/config/manifest changes. Do not implement B's metrics/SLOs or C's evaluator/annotation algorithm. Use named, explicit recording fakes until integration; never silent live success defaults.

### Test-first slices

1. Preserve baseline three-field output and one-call characterization.
2. Two-stage ordering; classifier parse failure skips drafting; draft cannot override classification.
3. Covered harm/discrimination promotes effective severity; negation fixtures do not automatically promote on keywords alone.
4. Drafting failure retains classification/urgency, marks manual-required and never routes.
5. Persist intake before processing; audit/version each stage; interrupted cases reconcile after restart.
6. Authorized review of the current draft plus fixed wording is required; reviewer category/severity changes invalidate stale draft approval.
7. Duplicate/concurrent requests and approvals do not double-charge through accidental retries or create duplicate queue entries; show explicit conflicts.
8. Feedback is revision-linked; C plans queue/label records, but A enforces authorization and transactional storage. A rating alone cannot change ground truth.
9. B's capacity helper is enforced before new intake/provider execution; release a reserved slot on every exit. Busy responses are explicit.
10. Grafana webhook auth/limits and idempotent persistence use B's adapter; do not write a second rule evaluator.

Use temporary SQLite, fake provider, injected clock and recording telemetry/evaluator/model-policy adapters. Imports and unit tests need no OpenAI key or network.

### Proposed commands

```powershell
uv run pytest tests\contracts -q
uv run pytest tests\test_baseline_contract.py tests\test_orchestration.py tests\test_contracts.py tests\test_safety_policy.py tests\test_review_flow.py tests\test_persistence.py tests\test_resilience.py tests\test_demo_controls.py -q
uv run ruff check .
uv run mypy src
```

Create and run one focused test before its implementation; these are final focused-suite commands, not a requirement to create every file at once.

Before merging PR-A, update from current `main`, then also run `uv run pytest -q` and `uv run ruff format --check .`. Smoke-test the API/UI in visibly labeled fixture mode. Record commands/results and base/final commit in the PR; rerun if commits change. PR-0 runs contract/static checks only, not these absent-application tests.

### Integration responsibilities

- You lead application wiring after each phase's contract tests pass.
- Replace fakes with B/C functions without schema casts or translation hacks.
- Own live database migrations and all case/annotation/label/incident writes.
- Do not let B/C modules import UI/API orchestration just to test pure logic.
- Own common manifests; merge dependency requests using the package manager. Do not install unrequested tooling preemptively.

### Stop and report

Live calls can incur provider charges and have no application spending caps. Do not invoke production services or touch B/C-owned files to get tests green. Report contract mismatches instead.

Hand off owned changes in the separate PR, actual red/green commands/results, startup instructions, sample fixture API request/response, open integration seams and risks. Show the UI's fixture-mode indicator; do not call it a live model demo. Do not merge a failing PR or push module changes directly to `main`.