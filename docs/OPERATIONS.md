# Operations runbook

## Local stack

- Start: `docker compose up --build`
- Tail logs: `docker compose logs -f --tail=150 api worker web`
- Stop: `docker compose down`
- Reset local database/Redis (destructive): `docker compose down -v`
- API liveness: `GET /health/live`
- API readiness (checks PostgreSQL and Redis): `GET /health/ready`

## Basic diagnosis

### API returns 503 / readiness fails

1. Inspect `docker compose ps`.
2. Inspect `docker compose logs db redis api`.
3. Confirm database and Redis health checks pass.
4. Confirm environment variables match Compose service DNS names (`db`, `redis`) inside containers.
5. Do not expose a partially healthy instance to the public load balancer.

### Deployments stay queued

1. Inspect `docker compose logs worker` and Redis health.
2. Confirm worker has the same `DATABASE_URL`, `REDIS_URL` and deployment driver configuration.
3. Inspect deployment row/status and associated logs.
4. Current code has a known queue crash window; recover manually only in local/dev and implement transactional outbox/reconciliation before production.

### Deployment says healthy but no app URL appears

This is expected in mock mode. Mock `HEALTHY` means the lifecycle simulation ran, not that a customer runtime is available. No application code is cloned or run.

### Database migration fails

1. Read the full migration error.
2. Do not delete a production volume to “fix” migrations.
3. Take a database backup, inspect migration state and use a reviewed forward migration or restoration plan.
4. Never edit a migration already applied to any shared environment; create a new revision.

## Incident handling minimums for future production

- Assign incident commander and technical lead.
- Record onset, affected tenants/services, known changes and timeline.
- Protect logs and audit evidence while redacting secrets.
- Contain unsafe workloads first (disable ingress / suspend service / isolate node).
- Communicate customer impact and next update time through the status page.
- Restore from a known-good immutable image or validated backup.
- Rotate affected credentials and assess data exposure.
- Complete a blameless post-incident review with tracked corrective actions.
