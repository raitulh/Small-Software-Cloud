# Architecture and design decisions

## Product boundary

Small Software Cloud is initially a **control plane** for projects, services, deployments, configuration metadata, operational history and usage. The current deployment driver is mock-only. The design must not imply that a live app is running unless a real, validated runtime integration has confirmed it.

## Service boundaries

- **Dashboard (Next.js):** user-facing console.
- **Control plane (FastAPI):** authentication, authorization, API validation, metadata lifecycle and quotas.
- **PostgreSQL:** authoritative state; Redis is not the source of truth for projects or deployments.
- **Redis + Arq:** asynchronous job transport and retries.
- **Worker:** processes deployment lifecycle jobs. The current worker calls a mock driver only.
- **Future build plane:** isolated, disposable builders that checkout a pinned commit and publish an immutable OCI image.
- **Future runtime plane:** a separately managed workload scheduler and hardened execution environment. It must not be reachable directly from the public control-plane API.
- **Future ingress:** a reverse proxy maps verified hostnames to healthy runtime instances.
- **Future telemetry:** logs/metrics/traces are separate from application state and must redact secrets.

## Current deployment state machine

`QUEUED -> BUILDING -> STARTING -> HEALTHY | FAILED` (and future cancellation states).

In the mock driver, `HEALTHY` means only “the simulated lifecycle succeeded.” UI, API descriptions and customer-facing messages must make the absence of a live workload clear. Do not use mock status as uptime data or a customer-facing reliability metric.

## Data principles

- Use UUID identifiers and timestamps in UTC.
- Use immutable deployment IDs, commit SHA and image digest once real builds exist.
- Keep organization ownership explicit on every tenant resource and authorize via membership on every query/action.
- Record actor and target in audit events for sensitive state changes.
- Avoid storing access tokens/secrets in logs.
- Add new schema changes as incremental Alembic migrations. The initial migration is a starting snapshot, not a reason to edit deployed migration history.

## Queue reliability gap

In the current alpha, a deployment row is committed before the job is published to Redis. If the API process crashes between these actions, a queued deployment may be stranded. The endpoint handles a direct Redis failure, but that does not eliminate the crash window. Before commercial release, implement a transactional outbox in PostgreSQL, publish outbox events with a retrying dispatcher, and reconcile old queued/running jobs.

## Multi-node future

Do not introduce Kubernetes solely to look “cloud-native.” First establish workload isolation, immutable release semantics, routing, health checks, quotas, node health, reconciliation, and operational metrics. Adopt an orchestrator when these requirements exceed the safe capacity of the chosen scheduler, and validate that its security model fits untrusted workloads.
