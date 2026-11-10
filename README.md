# Complaint Resolution Co-Pilot

This repository contains the shared contract and Python project foundation for
the Complaint Resolution Co-Pilot. Start with the six planning documents in
[`docs/planning/`](docs/planning/README.md), especially
[`shared-contract-v1.md`](docs/planning/shared-contract-v1.md).

## Foundation setup

Requirements: Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).
The `requirements.txt` file is provided for pip-based development setups; `uv`
is the recommended path because it honors the committed lockfile.

```powershell
uv sync --frozen
uv run pytest tests\contracts -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

For pip, create/activate a virtual environment, then run
`python -m pip install -r requirements.txt`.

`uv sync --frozen` installs only the project build backend and development
tools. There are no provider or application runtime dependencies.

## Current scope and limitations

The package defines validated shared records and interface contracts. Its three
synthetic fixtures cover a successful two-stage result, a model SEV3 prediction
with effective SEV1, and a drafting failure that retains successful
classification and urgency. Fixtures describe record shapes; they do not
execute agent or safeguard behavior.

This foundation does not include agents, orchestration, model/provider clients,
severity-promotion or model-routing logic, pricing calculations, incident
handling, API/UI, persistence, datasets, telemetry exporters, evaluation
algorithms, Docker/Compose, CI/CD, or Kubernetes. It makes no live-service calls
and requires no API keys.

Phase owners should raise future runtime dependency requests for review and add
them only with the phase that needs them; this foundation intentionally does
not pre-install speculative dependencies.

The initial contract proposes limits of 20,000 characters for complaint and
draft text, 2,000 for evidence quotes and feedback notes, and 4,000 for
classification summaries. These bounds, input-size bucket thresholds, failure
codes, and annotation priority semantics require A/B/C review before dependent
phase work treats them as frozen.
