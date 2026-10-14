# Security model and review checklist

This document is an engineering checklist, not a security certification. The current repository does not execute customer code and is not ready for public multi-tenant hosting.

## Threat model

Treat repository contents, Dockerfiles, dependencies, runtime processes, user-supplied environment variables, domain names and all customer requests as untrusted.

Threats to assess include:

- Cross-organization object access and insecure direct object references.
- Account takeover, brute force, credential stuffing and token theft.
- Secret leakage through UI, API errors, audit payloads, logs, build output or crash reports.
- SSRF, DNS rebinding, internal metadata endpoint access and unrestricted egress.
- Container or VM escape, privileged process abuse, host filesystem access and resource exhaustion.
- Malicious image/dependency, build-cache poisoning and artifact tampering.
- Phishing, spam, scanning, cryptomining, malware distribution and denial-of-service abuse.
- Webhook replay/forgery and OAuth/GitHub installation permission mistakes.
- Backup exposure, insecure deletion, unrotated keys and supply-chain compromise.

## Controls required before public workloads

1. **Identity:** verified email, account recovery, MFA option, rate-limited login, password policy, token revocation, session rotation and protection against brute force.
2. **Session model:** move production browser auth from `sessionStorage` bearer tokens to a secure HttpOnly, SameSite cookie/BFF pattern or a reviewed OIDC session design. Do not store long-lived credentials in browser storage.
3. **Authorization:** organization-scoped membership checks on all object access; test viewer/developer/admin/owner capabilities; include tenant IDs in queries where appropriate; consider PostgreSQL RLS as defense in depth.
4. **Secrets:** envelope encryption using a managed KMS or a separately protected key; key rotation; redaction; never return stored plaintext secrets by default.
5. **Build:** disposable build environments; restricted credential broker; no host Docker socket; minimal build network; bounded CPU, memory, disk and time; registry provenance/scanning; immutable image digests.
6. **Runtime:** no privileged containers; drop capabilities; read-only root filesystem where feasible; seccomp/AppArmor; namespaces/cgroups; egress policies; isolated metadata/control plane; evaluate gVisor or microVMs for untrusted code. Rootless containers alone are not a complete sandbox.
7. **Network:** no customer-to-customer access by default; protect cloud metadata; validate custom domains and prevent host-header poisoning; restrict management ports to private networks.
8. **Abuse:** registration and deployment throttles; resource quotas; suspicious-usage alerts; documented suspension, appeal and deletion procedures; provider abuse contacts.
9. **Supply chain:** pinned dependencies, automated dependency updates, SBOM, image scan, signed artifact/provenance policy where practical, protected CI secrets and least-privilege CI permissions.
10. **Observability:** structured logs without passwords/tokens; immutable audit events for privileged actions; alert on account abuse, node pressure, unusual egress and failed isolation tests.
11. **Recovery:** encrypted off-site backup, restore drills, RPO/RTO definitions, key recovery and incident runbooks.
12. **Review:** independent penetration test and remediation of critical/high findings before opening public signup.

## API-specific cautions

- JWTs are short-lived in this codebase but there is no refresh/revocation session system. Account-disable checks should be evaluated on protected API calls in a commercial release.
- Add rate limiting at the edge and account/IP level; per-organization deployment count is not a replacement for login or request throttles.
- Use strict request schemas, body-size limits, trusted proxy configuration and security headers.
- Do not include raw exception content in customer API responses.
- `CORS_ORIGINS` must contain exact trusted frontend origins, not `*` for a credentialed production app.
- Swagger/OpenAPI docs are disabled in production config; ensure reverse proxies and deployment config match this setting.
