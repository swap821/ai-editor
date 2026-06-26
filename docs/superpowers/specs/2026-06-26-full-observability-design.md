# Full observability stack — design spec

**Date:** 2026-06-26  
**Scope:** Close the `RENOVATION_PLAN.md` / `FUTURE_FRONTIER.md` observability gap beyond the MVP (`/metrics` endpoint + single-service compose). Deliver an operator-runnable local monitoring plane: Prometheus scraper, Grafana dashboard, Alertmanager rules, and RED-method request metrics.  
**Constraint:** Local-first / single-operator by default; no external alerting sinks required; no secrets in committed configs.

---

## Goal

The MVP exposes Prometheus text at `/metrics` and ships a one-service `docker-compose.yml`. That proves the mechanism but leaves the operator without an out-of-the-box way to see trends, correlate failures, or get alerted when the audit chain breaks. This slice turns the existing endpoint into a complete single-box observability plane.

Honest target: **~90% coverage of a single-operator monitoring setup** — metrics, dashboards, and two trust-critical alerts — not a multi-tenant SRE platform.

## Current state (from investigation)

- `aios/core/metrics.py` already has a dedicated `CollectorRegistry` with gauges for `DevelopmentTracker.summary()`, approval/autonomy counts, and audit-chain validity, plus a counter for audit-verify failures.
- `aios/api/main.py` serves `/metrics` and updates the collector per request.
- `docker-compose.yml` is a single `aios` service; there is no Prometheus, Grafana, or Alertmanager.
- `tests/test_metrics.py` verifies the endpoint output.
- `prometheus-client==0.21.0` is already in `requirements.txt`.
- No HTTP request-duration/rate/error metrics exist; no health endpoint is wired for probes.

## Approach

### 1. Add RED-method HTTP middleware metrics

Add a small FastAPI/Starlette middleware in `aios/core/metrics.py` (or a new `aios/api/middleware.py`) that records:

- `aios_http_requests_total` — Counter, labeled `method`, `route`, `status_code`.
- `aios_http_request_duration_seconds` — Histogram, labeled `method`, `route`.
- `aios_http_request_errors_total` — Counter for 5xx responses.

The middleware must be non-breaking: any exception inside it is caught and logged, never raised. It must also skip the `/metrics` route itself so scrapes do not self-amplify.

### 2. Add a `/health` probe endpoint

Add `GET /health` returning `{"status":"ok"}` and HTTP 200. Prometheus will use this as a black-box liveness probe; Grafana can surface uptime.

### 3. Extend the metrics collector

- Keep the existing dedicated registry for AI-OS semantic metrics.
- Optionally expose process metrics via the default `prometheus_client` registry on a separate port or merge them carefully so tests stay isolated. Decision: keep AI-OS metrics in the dedicated registry and expose only that on `/metrics`; process metrics are available through the Prometheus node exporter if the operator wants them.

### 4. Add Prometheus, Grafana, and Alertmanager services

Update `docker-compose.yml` to add:

- `prometheus` — official image, mounts `observability/prometheus.yml` and `observability/alert_rules.yml`, scrapes `aios:8000/metrics` every 15s.
- `grafana` — official image, mounts provisioning files under `observability/grafana/`: datasource (Prometheus), dashboard provider, and one AI-OS dashboard JSON.
- `alertmanager` — official image, mounts `observability/alertmanager.yml`. By default it logs alerts to stderr only; the operator can opt into a webhook by overriding `AIOS_ALERT_WEBHOOK_URL` in `.env`.

All three services use a shared Docker network `aios-net` so no ports need to be exposed to the host beyond Grafana (`3000`) and Prometheus (`9090`) optionally.

### 5. Grafana dashboard

One provisioned dashboard with three rows:

- **Trust posture:** `aios_audit_chain_valid`, `aios_audit_verify_failures_total`, `aios_human_intervention_rate`, `aios_blocked_actions_total`, `aios_approvals_total`, `aios_earned_autonomy_grants_total`.
- **Cognition throughput:** `aios_tasks_total`, `aios_verified_success_rate`, `aios_verification_coverage`, `aios_average_tool_calls`, `aios_lessons_total`, `aios_repeated_mistakes_total`.
- **Service health:** `aios_http_requests_total` rate, `aios_http_request_errors_total` rate, `aios_http_request_duration_seconds` p95, black-box `/health` uptime.

### 6. Alert rules

Two alert rules in `observability/alert_rules.yml`:

- `AiOSAuditChainBroken` — fires when `aios_audit_chain_valid == 0` for 1m.
- `AiOSHighInterventionRate` — fires when `aios_human_intervention_rate > 0.5` for 5m.
- `AiOSHighErrorRate` — fires when the rate of `aios_http_request_errors_total` exceeds 1 per minute for 5m.

Alertmanager default route logs to stderr; optional webhook route activated by `AIOS_ALERT_WEBHOOK_URL`.

## Files touched

- `aios/core/metrics.py` — add RED middleware helpers and request metrics.
- `aios/api/main.py` — register middleware, add `/health`.
- `docker-compose.yml` — add `prometheus`, `grafana`, `alertmanager` services and `aios-net` network.
- `observability/prometheus.yml` — new.
- `observability/alert_rules.yml` — new.
- `observability/alertmanager.yml` — new.
- `observability/grafana/datasources.yml` — new.
- `observability/grafana/dashboards/aios-dashboard.json` — new.
- `observability/grafana/dashboards/dashboard-provider.yml` — new.
- `tests/test_metrics.py` — add tests for middleware metrics and `/health`.
- `AGENTS.md` — document `docker compose up` observability usage.

## Testing plan

1. `tests/test_metrics.py` asserts RED-method counters and histogram labels appear after a request.
2. `tests/test_metrics.py` asserts `/health` returns 200.
3. `docker compose config` validates the compose file syntax.
4. `docker compose up --build -d` locally; verify Prometheus targets page shows `aios:8000` UP.
5. Verify Grafana loads the provisioned AI-OS dashboard and shows data.
6. Run the audit-verify failure test and confirm Alertmanager logs the `AiOSAuditChainBroken` alert.
7. Backend full suite and product typecheck/tests/build stay green.

## Security notes

- `/metrics` and `/health` remain unauthenticated. They expose only operational counters and "ok"; no secrets, transcripts, or file paths are emitted. In the Docker network, Prometheus reaches them over the internal `aios-net`; the host ports for Prometheus/Grafana are optional and can be omitted by the operator.
- Alertmanager webhook URL is injected from `.env`, never committed.
- No new network egress is required; the default sink is stderr.

## Out of scope

- Distributed tracing.
- Log aggregation (Loki/Promtail) — logs are already structured JSON on disk/stderr; a future slice can unify them.
- Long-term remote storage or cloud alerting.
- Auth inside Grafana/Prometheus — single-operator local run assumes the laptop boundary.

## Rollout

Operator runs:

```bash
AIOS_API_TOKEN=<32-char-token> docker compose up --build
```

Then opens http://localhost:3000 for Grafana (default credentials admin/admin, changed on first login) or http://localhost:9090 for Prometheus.
