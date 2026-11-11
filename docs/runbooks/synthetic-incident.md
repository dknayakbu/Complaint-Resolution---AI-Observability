# Synthetic incident rehearsal runbook

This runbook covers local fixture-mode incidents only. It does not authorize
OpenAI calls, customer data, real queue routing, or external notifications.

## Detect and triage

1. Confirm `/api/mode` reports `fixture`; do not troubleshoot a provider incident
   by switching to live mode.
2. Check Grafana's **Drift and Incident** dashboard and the alert inbox for the
   firing event. Inspect the matching API trace in Jaeger using its trace ID.
3. Check `/api/operations/slo`. It reports the latest 30 persisted completion
   events and must say `insufficient_sample` until all 30 are present.
4. Inspect the affected case. A provider/schema failure must be `manual_required`
   with no draft and no queue entry.

## Contain and recover

1. Stop submitting the controlled fault sample. Do not retry failed case IDs
   with altered complaint text.
2. Keep the affected case in manual review; never synthesize an acknowledgement
   or route it around reviewer approval.
3. Submit a new synthetic complaint with a new idempotency key and verify the
   two fixture stages succeed.
4. Wait for the alert's resolved webhook and verify both lifecycle events in
   `/api/alerts`. Repeated delivery of either event must be idempotent.
5. Recheck the SLI after enough fresh completions. A single success does not
   erase a failure from the latest-30 window; report recovery only when that
   window and the alert state support it.

## Limits

The controlled `synthetic-provider-timeout` fixture is a deterministic adapter
fault, not evidence that OpenAI or a production service failed. The local
webhook inbox and Grafana rules are rehearsal tooling, not an external paging
channel or production incident-management system.
