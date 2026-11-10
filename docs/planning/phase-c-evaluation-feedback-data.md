# Person C - Demo Data, Evaluation, Drift and Human Feedback

Share this file with [the plan](plan.md), [shared contract v1](shared-contract-v1.md) and [README](README.md). The target starts as a NEW BLANK repository, not an existing complaint service or the host repository.

## Copy-ready Copilot task

Implement Phase C only. Read the plan/shared contract; state scope, owned files, dataset limitations and first behavioral red test. Start with recorded results and raw synthetic inputs, not a live model.

### Blank-repository start and your separate PR

1. Review the shared types/fixtures and minimal dependency needs in A's PR-0, created from the new repository's README-only anchor. Authoring raw samples may start immediately, but do not assume application code exists.
2. After PR-0 tests/review pass and it merges, create `feat/phase-c-evaluation-feedback` from the merged `main` and open **PR-C** into `main`.
3. Build from recorded `AnalysisResult` fixtures and fake telemetry/judge/storage adapters. Do not import A's unmerged API/provider or B's unmerged instrumentation. Do not create another root manifest, shared contracts or migrations.
4. Development runs in parallel with A/B. Merge order is **PR-0 -> PR-A -> PR-B -> PR-C -> PR-I**. Before PR-C merge, update against `main` containing PR-A/B and rerun phase plus full-suite/static checks.
5. After merge, help review A's separate PR-I to connect live results, reviewer UI, persistence and exported evaluation metrics. Your PR-C remains a self-testable module/data PR.

If foundation types/configuration are absent, request PR-0 instead of reconstructing them privately.

### Own

`online_eval.py`, `eval.py`, `drift.py`, `feedback.py`, `data\`, evaluation/feedback/drift/phase-C tests; optional tone-comparison tests after the core work.

Do not change API authorization, storage/migrations, provider/model routing or Grafana rules. Return typed findings/annotation records for A to persist; send metric observations through B's interface.

### Raw data deliverables

1. Write the plan's 12 showcase complaints to `data\showcase\complaints.jsonl`; write the proposed answer key separately.
2. Create 30 distinct frozen holdout cases: 12 SEV1, 9 SEV2, 9 SEV3, all seven categories covered. Use separate input and label JSONL files.
3. Require a second human to adjudicate safety labels and ambiguous categories before freezing. Record provenance, label status, dataset version/hash and scenario-family split.
4. Prevent showcase/holdout family leakage. Keep full raw text; no real identifiers or copied customer complaints.
5. Create a separate input-drift stream: 30 baseline and two windows of 10 shifted raw complaints. Feature extraction is local and model-free; call it input-shift evidence.
6. Add malformed/provider-failure fixtures separately. They do not count as real model-quality observations.

The 150-case holdout is optional expanded evidence, not a prerequisite. Do not claim that 12 SEV1 holdout cases establish production safety.

### Evaluation slices - test first

- Loader rejects duplicate IDs, missing/invalid labels and split leakage; model input serializer rejects expected-label fields.
- Fixture confusion matrix, category/queue accuracy and raw/effective SEV1 recall have correct denominators. Missing labels yield unknown + coverage, not pass.
- Online rule checker consumes existing results/policy flags, not another agent invocation. It cannot know real classification correctness without labels.
- Draft faithfulness/tone uses the declared human rubric. An optional sampled judge is off by default, typed, separately budgeted and deterministically selected; timeout/parse failure is unknown, not score zero.
- Compare fixed-model versus proposed stage-tiered policy using the same frozen inputs and prompts/limits; separate classification safety, wording/unsupported-claim, tone, latency and cost. A cheaper model must pass gates before configuration changes.
- Keep optional manual tone comparison isolated from active case state and routing.

### Feedback/annotation slices - test first

- Merge negative human feedback and an evaluation failure on one case/revision into one pending item, preserving both reasons.
- A thumbs-down is not a ground-truth label and cannot change approval, routing or severity.
- Prioritize safety findings; preserve revision/evidence links and an auditable adjudication result.
- A enforces reviewer authorization and writes one versioned label transaction. Your pure functions do not directly update SQLite.
- Adjudicated corrections enter a candidate pool, not automatic training or the frozen holdout. Repeated processing cannot double-count a correction/miss.

### Drift slices - test first

- Compute documented normalized JSD from fixed input-topic/length features.
- Recent window >=10, baseline >=30; two consecutive non-overlapping eligible windows above 0.10 are a proposed toy warning, pending calibration.
- Low sample, empty/zero bins and missing baselines return explicit ineligible state.
- Input shift alone is not quality regression; one confirmed SEV1 miss does not wait for drift windows.

### Proposed commands

```powershell
uv run pytest tests\contracts tests\test_feedback_eval.py tests\test_drift.py tests\phase_c -q
uv run python -m complaint_copilot.eval --mode fixture --inputs data\eval\holdout_inputs.jsonl --labels data\eval\holdout_labels.jsonl
uv run ruff check .
uv run mypy src
```

Use fake judges and recorded analysis results. Imports/tests need no OpenAI credentials. A live evaluation must require separate explicit approval, `--allow-live-model`, bounded call/token/cost controls and recorded configuration.

Before PR-C merge, also run `uv run pytest -q` and `uv run ruff format --check .` on the final branch updated with PR-A/B. Record base/final commit, dataset/label versions, adjudication status and actual commands/results in the PR. Unreviewed labels remain explicitly unreviewed; never claim sign-off from generated data alone.

### Stop and report

Do not fetch production complaints, manufacture customer records, tune on holdout failures and call them unseen, or silently change shared schemas. No live/purchased calls by default.

Hand off your separate PR, dataset manifests and label status, raw/answer-key separation, exact tests/results, sample quality report, annotation before/after example, drift eligibility/output, scoring rubric, integration functions and remaining statistical/labeling risks. Distinguish fixtures, human labels and real model measurements. Do not merge directly to `main` or skip failing gates.
