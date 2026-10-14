# Contributing

1. Create a branch for each change and explain the user or operational problem it solves.
2. Add or update automated tests for schema, authorization and lifecycle changes.
3. Never add real credentials, production database dumps or customer source code to the repository.
4. Treat any new feature that executes customer code as a security-sensitive architectural change. Update the threat model and production gap checklist before implementation.
5. Add incremental Alembic migrations; never rewrite a migration already applied to shared environments.
6. Run `pytest`, `ruff check .`, and the dashboard typecheck/lint/build before submitting when dependencies are available.
7. Update documentation, operational runbooks and tests alongside changed API contracts.

## Definition of done

- API and UI behavior matches documented product states (mock state must never be represented as a real deployment).
- Authorization is checked server-side for every tenant-owned resource.
- Failure cases, retries and observability are covered.
- No secrets or unsafe default production access are introduced.
- Relevant docs and production readiness gates are updated.
