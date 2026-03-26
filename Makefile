.PHONY: docker-up docker-down docker-logs backend-install backend-dev frontend-install frontend-dev test-backend lint-frontend build-frontend verify

docker-up:
	docker compose up -d postgres

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f postgres

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e .

backend-dev:
	cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3000

test-backend:
	cd backend && .venv/bin/python -m pytest tests

lint-frontend:
	cd frontend && npm run lint

build-frontend:
	cd frontend && npm run build

verify: test-backend lint-frontend build-frontend
