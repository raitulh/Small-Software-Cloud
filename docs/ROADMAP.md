# A-to-Z product and engineering roadmap

## Stage 0 — Validate the problem

- Interview 15–25 student developers, freelancers and indie founders.
- Observe their current deploy workflow and identify failure points.
- Compare Vercel, Render, Railway, Fly.io and self-hosted alternatives using current docs/pricing.
- Choose one initial segment; avoid marketing to “everyone who writes software.”
- Write a one-page value proposition and test willingness to pay before expensive infrastructure spend.

## Stage 1 — Control-plane foundation

- [x] Auth basics and organization membership model.
- [x] Projects/services/deployment metadata.
- [x] PostgreSQL + Alembic and Redis + Arq.
- [x] Basic quotas, audit events and health endpoints.
- [x] Dashboard and local compose.
- [x] Explicit mock lifecycle.
- [ ] Production sessions, verification/recovery, advanced authorization tests.
- [ ] Outbox and job reconciliation.

## Stage 2 — Real build plane (not yet implemented)

- GitHub App with least-privilege repository installation and validated HMAC webhook delivery.
- Checkout pinned commits using short-lived scoped credentials.
- Disposable build execution without host socket exposure.
- Build cache keyed by verified inputs; cache isolation per trust domain.
- Produce OCI image; scan it; store immutable digest and provenance metadata.
- Ensure build artifacts and logs have retention and deletion policies.

## Stage 3 — Real runtime (not yet implemented)

- Select workload isolation approach based on threat model, compliance needs and cost.
- Build a node agent with authenticated outbound control channel and narrowly scoped commands.
- Enforce cgroups/quotas, filesystem policy, seccomp/AppArmor, network restrictions and termination semantics.
- Implement desired-state reconciliation: database stores intended state; agent reports observed state; controller converges safely.
- Health-gated release switch and rollback to prior immutable digest.
- Validate node drain, process crash, disk pressure and network partition behavior.

## Stage 4 — Networking and domains (not yet implemented)

- Generated subdomains, host verification and safe routing.
- Automated TLS issuance and renewal, rate-limit-aware retry.
- Custom domain TXT/HTTP verification, pending/verified/failed lifecycle, safe deletion.
- Internal port exposure model; only explicitly configured ports public.
- Egress restrictions and metadata endpoint blocks.

## Stage 5 — Reliability and commercial operations

- OpenTelemetry-style structured metrics/logs/traces.
- Encrypted off-site backups and tested restore procedures.
- Incident response, status page, on-call/escalation model.
- Usage metering based on measured runtime, storage, egress and build consumption.
- Quota enforcement outside customer containers; soft alerts and hard caps.
- Separate operational cost from user-facing list price; study idle capacity and abuse rates.

## Stage 6 — Private beta and launch gate

- Onboard a small set of trusted beta customers in an isolated staging environment.
- Capture activation, build success, deployment time, error rate, resource cost and 30-day retention.
- Run isolation/SSRF/abuse/load/restore exercises.
- Fix critical/high findings and validate support processes.
- Release publicly only after product, security, reliability and unit economics gates pass.

## Stage 7 — Expansion

- Add background workers/scheduled jobs after runtime lifecycle is stable.
- Add managed database provisioning only with customer-specific backup/restore and deletion guarantees.
- Add bring-your-own-server after the managed deployment path is well understood.
- Add additional runtimes and regions based on customer demand, not feature count.
- Consider a stronger orchestrator only when operational evidence requires it.

## Proposed internal alpha targets (not customer promises)

- First clean repository-to-staging deployment under 5 minutes for a small app.
- 95%+ successful deployments in repeated known-good test suite.
- Rollback to last known-good release under 2 minutes in test environment.
- Restore drill passes against documented RPO/RTO.
- Zero unresolved critical/high security findings before public arbitrary-code execution.
- Positive contribution margin for representative paid usage scenarios.
