# Complaint-Resolution---AI-Observability
Complaint Resolution - AI Observability

# Complaint Resolution Co-Pilot - Start Here

This folder is the complete, shareable **planning pack**. It is not application code. The eventual project starts from a **new blank repository**, with no dependency on the repository currently holding this folder.

## What to share

Share all six Markdown files together, preserving their names:

| File | Purpose / reader |
| --- | --- |
| [plan.md](plan.md) | Requirements, architecture, synthetic showcase complaints, evaluation, operations and exact PR test/merge flow; everyone reads it |
| [shared-contract-v1.md](shared-contract-v1.md) | Shared types, records, interfaces, failure/unknown semantics and fixture requirements; everyone agrees before coding |
| [phase-a-complaint-workflow.md](phase-a-complaint-workflow.md) | Person A: foundation PR, then separate workflow/API/UI/storage PR, then integration PR |
| [phase-b-agentops-operations.md](phase-b-agentops-operations.md) | Person B: separate AgentOps/M6/M7 PR |
| [phase-c-evaluation-feedback-data.md](phase-c-evaluation-feedback-data.md) | Person C: separate data/evaluation/drift/feedback PR |
| [README.md](README.md) | Blank-repository setup, reading order and workflow summary |

The original assignment document is not included. The plan summarizes Team 2's requirements and preserves facilitator-approval prerequisites. The 12 raw showcase examples and answer key are in the plan; JSONL datasets and application code are future implementation work, not files missing from this pack.

## Starting from a blank repository

1. Create a NEW target repository for this assignment. Initialize its `main` branch with a minimal README anchor commit; a repository with no commits has no PR base.
2. Clone it into a separate directory. Do not use this host repository or this documentation folder as the application's working directory.
3. Give everyone a copy of this pack. Person A includes all six files under `docs\planning\` in foundation PR-0. Keep the new repository's root README separate.
4. All three owners read the plan and contract. A prepares only the minimal foundation: Python 3.12 package/configuration, lockfile, shared types and three contract fixtures.
5. Review/test/merge PR-0. Only then create all three module branches from that merged `main`.

No phase assumes a pre-existing API, provider adapter, application package, dataset, telemetry stack, manifest or lockfile. PR-0 creates the common minimum; each phase creates its assigned module from that base. B/C can prepare raw inputs/test vectors while PR-0 is reviewed, but must not generate competing scaffolds.

## Separate PRs and exact merge order

The following are logical labels, not actual GitHub PR numbers. Every PR targets `main`.

```text
New blank repo -> README anchor on main -> PR-0 foundation
                                             |
                      +----------------------+----------------------+
                      |                      |                      |
                 PR-A workflow          PR-B AgentOps          PR-C evaluation
                      |                      |                      |
                      +------ parallel development after PR-0 ------+

Test/review/merge: PR-0 -> PR-A -> PR-B -> PR-C -> PR-I integration
```

| Label | Owner | Branch | When to test / merge |
| --- | --- | --- | --- |
| PR-0 | A; B/C review | `chore/foundation` | Contract/static checks first; merge before module branches start |
| PR-A | A | `feat/phase-a-workflow` | Contract + A tests, full available suite, static checks and fixture UI/API smoke; first module merge |
| PR-B | B | `feat/phase-b-agentops` | Develop independently; update with merged PR-A, then phase/full/static/telemetry checks before merge |
| PR-C | C | `feat/phase-c-evaluation-feedback` | Develop independently; update with merged PR-A/B, then phase/full/static/data checks before merge |
| PR-I | A leads; B/C review | `feat/integration-demo` | Branch after all modules merge; wire actual modules and prove stack/safety/feedback integration |

Detailed evidence and gates are in **Section 10.7 of [plan.md](plan.md)**. Refresh each feature branch from current `main` and rerun tests on the final commit before merge. Do not bypass failed checks or treat an earlier commit's results as current.

Parallel work does not mean three unrelated repositories or three copies of shared contracts. It also does not require merging B/C before their code is ready. If a phase is delayed, keep dependent merge/integration gates open rather than hiding missing functionality.

## Giving the task to Copilot

In the NEW target repository, attach this README, the plan, shared contract and the person's handoff. State:

> Implement only my assigned phase in this new repository. Treat it as a blank-start project, not an extension of another application. Follow the agreed PR-0 prerequisite and create a separate phase PR. Read the plan and contract, state your scope/owned files and first failing behavioral test, then work test-first with explicit fixtures. Do not call paid models or modify another phase without approval. Report contract mismatches instead of inventing substitutes.

For A, run the **PR-0 task first**, review/merge it, then use a new branch/task for PR-A. B/C do not run A's foundation implementation task. Everyone uses the same merged contract.

The handoffs are ordinary Markdown task briefs, not automatically loaded Copilot customization files. Attach/read them explicitly.

## Rules that keep the demo simple and honest

- Two agents only: classification then acknowledgement drafting; orchestrator stays inside Agent layer.
- Synthetic data, human approval and simulated queues only.
- Stage-based model selection is evaluated; no response cache, Redis, extra agent framework, release engineering, CI/CD or Kubernetes.
- Tests use fakes without credentials; fixture output is visibly labeled.
- Live OpenAI calls have no application spending caps; provider charges and limits apply.
- Fixture integration evidence does not substitute for genuinely verified live-demo evidence.
- Three builders do not replace the assignment's six-member document/presentation/demo participation requirement.

## Status of this pack

Only documentation is being supplied. No target repository, implementation branch, commit or GitHub PR has been created by this packaging task. No application tests, Docker workloads or model calls have run. Validate the implemented project later using the per-PR gates, not this pack's presence.
