# Complaint Resolution Co-Pilot

This repository contains the shared contracts and Phase A/B/C modules, plus a
local complaint application and observability stack. Fixture mode is the safe
default and uses scripted responses. A separately approved live mode sends
invented complaint text to configured OpenAI models. Both modes use a local
SQLite database and simulated queues; neither sends complaints to a real queue
or sends external notifications.

## Run the local synthetic demo

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and Docker with
the Compose plugin. From the repository root, run these commands in
PowerShell. Ensure `.env` has `APP_MODE=fixture` before starting; this path
uses scripted provider responses only. Each service starts after its dependency
is ready:

```powershell
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Compose configuration is invalid" }

function Wait-HttpOk([string]$Uri) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Service did not become ready: $Uri"
}

docker compose up -d jaeger
if ($LASTEXITCODE -ne 0) { throw "Jaeger failed to start" }
Wait-HttpOk http://localhost:16686/

docker compose up -d otel-collector
if ($LASTEXITCODE -ne 0) { throw "OpenTelemetry Collector failed to start" }
Wait-HttpOk http://localhost:8888/metrics
Wait-HttpOk http://localhost:8889/metrics

docker compose up -d prometheus
if ($LASTEXITCODE -ne 0) { throw "Prometheus failed to start" }
Wait-HttpOk http://localhost:9090/-/ready

docker compose up -d grafana
if ($LASTEXITCODE -ne 0) { throw "Grafana failed to start" }
Wait-HttpOk http://localhost:3000/api/health

docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "Complaint API failed to start" }
Wait-HttpOk http://localhost:8000/health
$mode = Invoke-RestMethod http://localhost:8000/api/mode
if ($mode.mode -ne "fixture") { throw "The demo must run in fixture mode" }

docker compose up -d ui
if ($LASTEXITCODE -ne 0) { throw "Streamlit UI failed to start" }
Wait-HttpOk http://localhost:8501/_stcore/health
docker compose ps

uv run python scripts\demo_rehearsal.py
```

The rehearsal verifies the one-call baseline; the two-stage fixture journey;
authorized current-revision approval and one simulated queue entry; a
controlled model SEV3/effective SEV1 miss; revision-linked feedback and
adjudication; essential-funds safeguarding, negation, and injection
containment; duplicate alert suppression; automatic Grafana alert firing and
resolution for a controlled fixture provider failure; synthetic
drift/cost/quality/SLO replays; the persisted latest-30 SLI endpoint; a real
application trace in Jaeger; Prometheus scrape health; and the three provisioned
Grafana dashboards.

The UI is at <http://localhost:8501>. The API health and mode endpoints are
<http://localhost:8000/health> and <http://localhost:8000/api/mode>. The
observability interfaces are Jaeger at <http://localhost:16686>, Prometheus at
<http://localhost:9090>, and Grafana at <http://localhost:3000>. Grafana's
local demo defaults are `admin` / `admin`; override them with ignored `.env`
settings before starting Grafana. The default reviewer/internal tokens are
fixture-only values; do not reuse them outside this local demo.

The API also exposes `/api/model-policy` (explicit stage assignments) and
`/api/operations/slo` (latest 30 persisted terminal workflow outcomes). The
SLI reports `insufficient_sample` until its complete 30-record window exists;
the 99% value is a planning target, not a calibrated or production SLO. The
quality replay scores outputs from the scripted fixture provider; its Q1 pack
is a separate controlled scenario built from synthetic labels, not a
model-to-model comparison. `CLASSIFICATION_MODEL`, `DRAFTING_MODEL`, and
`EVALUATION_MODEL` override the shared `MODEL_NAME` per stage; model selection
is explicit by stage and never based on predicted complaint severity.

Stop the containers while preserving the local demo and Grafana volumes:

```powershell
docker compose down
```

Do not add `-v` unless you intentionally want to remove the named volumes and
their local SQLite/Grafana state.

## Run an approved live-model demo

Live mode makes real provider calls that may incur charges. It is disabled by
default. Use **invented complaint text only**, and enable it only after the
demo owner has approved the provider, models, request count, call count, token
limit, and maximum spend. Never paste an API key into chat or commit it.

1. If you do not already have a local `.env`, copy the safe template and edit
   it locally:

   ```powershell
   Copy-Item .env.example .env
   code .env
   ```

   Do not overwrite an existing `.env`; it may contain local credentials.
2. Set `APP_MODE=live` and fill in `OPENAI_API_KEY`. Replace both fixture
   tokens with private, sufficiently strong values:
   `REVIEWER_TOKEN` and `INTERNAL_TOKEN`.
3. Only after explicit approval, set `LIVE_MODEL_APPROVED=true` and a new,
   unique `LIVE_MODEL_APPROVAL_ID`. Fill every `LIVE_MODEL_MAX_*` value:
   - `LIVE_MODEL_MAX_REQUESTS` counts baseline requests and complaint intakes.
   - `LIVE_MODEL_MAX_CALLS` counts every provider attempt, including retries.
     One successful two-stage complaint needs two calls; with
     `PROVIDER_MAX_ATTEMPTS=2`, reserve up to four calls per complaint.
   - `LIVE_MODEL_MAX_TOKENS` is the maximum reserved token total.
   - `LIVE_MODEL_MAX_COST_USD` is the maximum reserved cost.
   - `LIVE_MODEL_MAX_OUTPUT_TOKENS` caps each model response.
   - `LIVE_MODEL_MAX_USD_PER_1K_TOKENS` must be at least the highest current
     input or output token rate for every configured stage model.

   Compute limits for the planned number of baseline/intake requests, configured
   retries and worst-case prompt/output size. Limits are hard local reservations;
   failed attempts are not refunded. They are not a provider-side spending cap.
   A used approval ID cannot be reused with changed limits.
4. Set `MODEL_NAME` and, if desired, `CLASSIFICATION_MODEL`,
   `DRAFTING_MODEL`, and `EVALUATION_MODEL`. For the first live run, using one
   reviewed model for classification and drafting makes the configuration
   easier to explain. Set `SHORT_INPUT_MAX` and `MEDIUM_INPUT_MAX` to positive,
   ordered character-count thresholds for short/medium/long telemetry buckets.
   API complaints are limited to 20,000 characters.
5. Start or recreate the configured services:

   ```powershell
   docker compose config --quiet
   if ($LASTEXITCODE -ne 0) { throw "Compose configuration is invalid" }
   docker compose up -d --build
   ```

6. Confirm <http://localhost:8000/api/mode> reports `"mode": "live"`,
   `"provider": "openai"`, and `"live_approved": "true"`. The UI must display
   **LIVE MODE** and the configured limits. If any value is wrong, stop and
   correct `.env` before submitting anything.
7. Open <http://localhost:8501>. Enter one short, fictional complaint in
   **Complaint intake** and submit it. The fixture-ID field is not shown in
   live mode. A completed case normally makes one classification call followed
   by one drafting call; retries consume additional approved calls. If
   classification or drafting fails, the UI shows the explicit manual-required
   state rather than a fabricated result.
8. In **Reviewer queue**, inspect the category, original model severity,
   safeguarded effective severity and draft. Approve only the current revision
   to create one simulated queue entry.
9. Open the case trace in Jaeger using the trace reference shown in the UI.
   Classification and drafting spans identify requested/served model and
   available token usage, without adding complaint text to telemetry. Prometheus
   and Grafana show application-level live-mode counts and trends.

The complaint text must be invented, not actual random customer data. Model
outputs and categories can vary, and safeguards only promote urgency for their
covered signals; do not expect an artificial raw-model miss. The
`scene-2-controlled-raw-miss` ID is a deterministic `FixtureProvider` switch in
`src/complaint_copilot/provider.py`; it is unavailable in live mode and is not
sent to the live model. The same applies to the fixture timeout ID.

Live cost is a conservative estimate from reported token usage at the approved
maximum rate for both input and output tokens; it is not the provider's actual
bill. Fixture-mode cost uses the repository's versioned fixture pricing table.
Verify the approved rate against current prices before presenting dollar
amounts. If a call is retried and earlier attempt usage is unavailable, the
stage cost is reported as unknown rather than counting only the final response.
Do not run
`scripts\demo_rehearsal.py` in live mode; it is a fixture-only acceptance
rehearsal. To return to the safe fixture mode, set
`APP_MODE=fixture`, keep the approval flag false, then run
`docker compose up -d --build api ui` and verify `/api/mode` before continuing.

## Checks

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
docker compose config --quiet
```

The test suite uses fakes and temporary databases. It makes no external model
calls or notifications. Ruff exempts only the long synthetic text literals in
`tools/generate_phase_c_data.py` from the 88-character line-length check.

## Scope and limitations

- Fixture mode is scripted behavior, not a genuine model demonstration,
  measured model accuracy, or a production-readiness claim.
- Replay values use the existing Phase B/C calculations over synthetic
  records. The drift scores are the extractor's observed values and may differ
  from planning estimates; synthetic labels are not independently adjudicated
  ground truth, and cost totals are not invoices.
- Grafana rules deliver firing/resolved events to the authenticated local inbox.
  The controlled provider timeout is a deterministic fixture fault, not a live
  provider incident. This is not an external paging channel or blind incident
  rehearsal.
- Live mode is rejected unless `LIVE_MODEL_APPROVED=true`, a non-empty
  `LIVE_MODEL_APPROVAL_ID`, and explicit `LIVE_MODEL_MAX_REQUESTS` (1-10),
  `LIVE_MODEL_MAX_CALLS` (1-60), `LIVE_MODEL_MAX_TOKENS`, and
  `LIVE_MODEL_MAX_COST_USD` limits are configured alongside live credentials
  and reviewer/input settings. `LIVE_MODEL_MAX_OUTPUT_TOKENS` (1-4096) caps
  every generation. `LIVE_MODEL_MAX_USD_PER_1K_TOKENS` is the approved
  conservative rate ceiling and must be at least the highest current input or
  output rate for any configured stage model. Before each provider attempt, the
  app reserves a conservative token amount (UTF-8 prompt bytes plus the output
  cap) and its cost at that rate; failed attempts are not refunded. Request,
  call, token, and cost reservations persist by approval ID and cannot be
  increased or changed under that ID. Choose fresh limits and a fresh approval
  ID for a separately approved run. The counters are hard local controls, not
  provider invoices or a substitute for provider-side spend limits. This task
  did not authorize or make a paid model call; approval-dependent live evidence
  remains pending.
- Real customer data, real queues, regulatory-approved wording, and external
  notifications remain out of scope.
