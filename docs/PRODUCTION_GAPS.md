# Production gap checklist — do not skip

The repository is a foundation. A public hosting product must not launch merely because `docker compose up` works.

## Not implemented in this release

- Real repository checkout, build execution, artifact registry and image scanning.
- Real workload startup, service routing, TLS/custom-domain automation, runtime health checks, live logs, CPU/RAM measurements or rollback of actual applications.
- Hardened build sandbox, workload sandbox, node scheduler, placement, node draining or reconciliation.
- GitHub App installation flow and signed webhook handling.
- Transactional outbox and stale-job reconciler for reliable job dispatch.
- Production browser session/BFF, email verification, password recovery, MFA, OIDC, API token lifecycle and account revocation.
- Complete tenant isolation proof, security assessment, abuse response system, billing provider integration, customer-facing usage settlement or SLA.
- Managed database provisioning, tenant data backups, automatic off-site restore, data export/deletion workflow, regional failover and capacity autoscaling.
- Production secret/KMS integration, WAF/rate limit deployment and independent penetration test.

## Gates before inviting private pilot customers

- [ ] Deploy only to a staging network and never claim mock deployments are live.
- [ ] Establish threat model, security owner and incident escalation contact.
- [ ] Validate tenant authorization with negative tests across every route.
- [ ] Replace browser token storage with a reviewed production session strategy.
- [ ] Implement login/signup limits, email verification and account recovery.
- [ ] Implement PostgreSQL transactional outbox and queue reconciliation.
- [ ] Verify container images run non-root and contain no secrets.
- [ ] Define backup/restore scope and pass a restore drill.
- [ ] Add metrics, alerting and operational dashboards.
- [ ] Perform dependency, image and secret scanning in CI.

## Gates before any public customer-code execution

- [ ] Threat model updated specifically for hostile Dockerfiles and arbitrary code.
- [ ] Disposable build workers tested for credential and filesystem isolation.
- [ ] Runtime isolation model selected and independently reviewed (e.g. hardened containers plus gVisor, or per-workload microVMs where threat model demands).
- [ ] Host Docker socket and privileged host APIs are never exposed to customers or customer containers.
- [ ] Network policies block metadata endpoints, control plane, internal databases and cross-tenant paths by default.
- [ ] CPU, memory, disk, PID, bandwidth and execution-time caps enforced outside customer control.
- [ ] Registry permissions scoped; images addressed by immutable digest; scanning/provenance policy enforced.
- [ ] Domain verification, host-header checks, TLS issuance and renewal tested.
- [ ] Abuse detection, workload suspension and incident handling tested.
- [ ] Escape, SSRF, cross-tenant and exhaustion tests passed.
- [ ] Independent security review/penetration test completed and critical/high findings fixed.
- [ ] Load tests, node failure tests, backup restore and operational drills passed.

## Go/no-go

Do not launch public arbitrary-code hosting while any security isolation item is unchecked. Keep the mock driver or run only trusted internal demo software until a real runtime is validated.

The current API configuration intentionally refuses `CLOUD_ENV=production` while `ALLOW_SIGNUPS=true`. Set signup to false for any isolated production-like control-plane deployment. This guard does not make the repository a production hosting provider; public workload execution remains unimplemented and must not be enabled with a host Docker socket.
