# API overview

Interactive OpenAPI documentation is enabled in local development at `/docs`. Production config disables Swagger/OpenAPI endpoints by default.

All routes under `/v1` (except registration/login) expect `Authorization: Bearer <access_token>`. Tokens are short-lived. This is a development session model; production should use a reviewed secure cookie/BFF or OIDC approach, revocation/session lifecycle, verified email and account recovery.

## Authentication

- `POST /v1/auth/register` — create user, default organization and owner membership.
- `POST /v1/auth/login` — authenticate and issue access token.

## Organizations & Workspaces

- `GET /v1/organizations` — list workspaces the user belongs to with role.
- `POST /v1/organizations` — create a new organization/workspace.
- `GET /v1/organizations/{org_id}` — fetch organization details.
- `GET /v1/organizations/{org_id}/members` — list organization team members.

## Projects and Services

- `GET /v1/projects` — list projects (supports optional `?organization_id=...` filter).
- `POST /v1/projects` — create project in specified or active workspace.
- `GET /v1/projects/{project_id}` — get project details.
- `PATCH /v1/projects/{project_id}` — update project name or description.
- `DELETE /v1/projects/{project_id}` — delete project and cascade delete services.
- `GET /v1/projects/{project_id}/services` — list services for project.
- `POST /v1/projects/{project_id}/services` — create new service.
- `GET /v1/services/{service_id}` — get service details.
- `PATCH /v1/services/{service_id}` — update service configuration (name, branch, repo, ports, memory, CPU).
- `DELETE /v1/services/{service_id}` — delete service.

## Environment Variables & Configuration

- `GET /v1/services/{service_id}/env` — get service environment variables (supports `?reveal=true` for developers/admins).
- `PUT /v1/services/{service_id}/env` — bulk set/update environment variables and secrets.

## Deployments

- `POST /v1/services/{service_id}/deployments` — queue a deployment lifecycle execution.
- `GET /v1/services/{service_id}/deployments` — list recent deployments.
- `GET /v1/deployments/{deployment_id}` — get deployment status.
- `POST /v1/deployments/{deployment_id}/cancel` — cancel a queued or running deployment.
- `GET /v1/deployments/{deployment_id}/logs` — read deployment logs.

## Dashboard Composite & Usage

- `GET /v1/dashboard/overview` — single-request composite endpoint returning organization, nested projects, services, latest deployments, and usage (eliminates N+1 client waterfalls).
- `GET /v1/usage` — get resource quotas and summary (supports optional `?organization_id=...`).
- `GET /health/live` — API liveness check.
- `GET /health/ready` — database and Redis readiness check.

## Response/permission rules

- Use UUID resource IDs and ISO-8601 timestamps.
- Mutations return a request ID header (`X-Request-ID`) for support/debugging.
- Object access is strictly verified against organization membership.
- API errors do not reveal internal exceptions, credentials or secrets.
