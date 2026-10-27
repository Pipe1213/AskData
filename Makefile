.PHONY: docker-up docker-down docker-logs load-dataset reload-schema-cache backend-install backend-dev frontend-install frontend-dev test-backend lint-frontend build-frontend verify eval eval-test eval-expected

DATASET ?= pagila
LABEL ?= run
SPLIT ?= all

docker-up:
	docker compose up -d postgres

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f postgres

load-dataset:
	./backend/scripts/load_dataset.sh $(DATASET)

reload-schema-cache:
	curl -fsS -X POST http://127.0.0.1:8000/schema/reload

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

eval-test:
	python3 eval/test_score.py

eval:
	./backend/scripts/load_dataset.sh $(DATASET)
	-curl -fsS -X POST http://127.0.0.1:8000/schema/reload > /dev/null
	python3 eval/score.py --dataset $(DATASET) --split $(SPLIT) --label $(LABEL)

eval-expected:
	./backend/scripts/load_dataset.sh $(DATASET)
	backend/.venv/bin/python eval/build_expected.py --dataset $(DATASET) --dsn postgresql://postgres:postgres@localhost:55432/pagila
