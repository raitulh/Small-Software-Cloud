.PHONY: up down logs api-test api-lint web-check
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f --tail=150
api-test:
	cd apps/api && pytest
api-lint:
	cd apps/api && ruff check .
web-check:
	cd apps/web && npm run typecheck && npm run lint && npm run build
