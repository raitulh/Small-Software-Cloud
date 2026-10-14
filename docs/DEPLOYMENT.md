# Deployment and environment guide

This is a deployment guide for the **control-plane preview**, not for running arbitrary customer apps. Do not expose it as a public hosting service until all production gates are completed.

## Local Docker Compose

See the repository root README. Compose binds web/API to `127.0.0.1` and uses dev-only database credentials. Never reuse these settings on a reachable server.

## Staging deployment (control plane only)

A staging deployment should use:

- A private/internal network for PostgreSQL and Redis. They must not have public ports.
- TLS at a reverse proxy or managed platform; redirect HTTP to HTTPS.
- Unique secrets injected at runtime from a secret manager.
- `CLOUD_ENV=staging`, exact `CORS_ORIGINS`, `ALLOW_SIGNUPS=false` after initial testers have been invited, and non-default passwords.
- An external monitoring endpoint for the readiness check.
- Separate staging database, Redis, image registry and storage credentials from any production environment.
- Network policy preventing staging from reaching production databases, metadata endpoints or workload control planes.

Before promotion, review migrations, verify restore points, run API/UI tests and confirm there is a documented rollback plan.

## Production hardening requirements

1. Use a managed database or hardened private PostgreSQL with encryption, automated backups, point-in-time recovery and monitored capacity.
2. Use private Redis or a managed equivalent with access control, TLS and persistence appropriate for job transport. Job durability still requires an outbox/reconciler.
3. Deploy API and worker with separate service identities and least-privilege network permissions.
4. Pin base images and dependencies; scan images/dependencies; rebuild regularly for security patches.
5. Use managed secret storage and rotating keys; never bake secrets into build arguments or layers.
6. Place the API behind a TLS reverse proxy, edge request limits, body-size limits and trusted proxy configuration.
7. Enable external alerting, log retention, database connection saturation alerts and tested backup/restore.
8. Complete `SECURITY.md` and `PRODUCTION_GAPS.md` before public use.

## Why there is no one-command public deploy

The repository does not yet include a hardened runtime agent/scheduler, real builder, registry workflow, domain/certificate controller, secret manager adapter, abuse-response system or independent security validation. Wiring Docker socket execution into the API would be a dangerous shortcut, not production readiness.
