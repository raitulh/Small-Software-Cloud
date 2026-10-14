# Validation status for this packaged revision

Validation is recorded transparently; a static code check is not a substitute for a clean container build and integration test.

## Checks completed in the authoring environment

- Python `compileall` over API, migrations and test files: passed.
- Pydantic settings/schema tests: 7 passed in the available environment.
- API full test suite: not fully executable here because the preinstalled Python environment did not include `pwdlib`; dependency installation was attempted but the environment could not resolve external package hosts.
- Docker Compose build/up: not run because Docker Engine/Compose is not available in the authoring environment.
- Next.js npm install/typecheck/lint/build: not completed because package installation did not finish in the network-restricted authoring environment.

## First verification to run on your machine

```powershell
Copy-Item .env.example .env
python scripts/generate_secret.py
# Paste the generated value into JWT_SECRET_KEY in .env

docker compose up --build
```

Then visit `http://localhost:3000` and `http://localhost:8000/health/ready`. Create an account, a project and a service, then run the deployment simulation. Confirm the UI labels it as simulated and does not show a live URL.

Before relying on it, run `docker compose logs -f --tail=150`, complete API unit tests in the API container/environment, and manually verify signup/login, role isolation, project/service creation, queue processing, logs, and restart/recovery behavior.
