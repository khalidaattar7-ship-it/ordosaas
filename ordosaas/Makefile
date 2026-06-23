.PHONY: up down logs test migrate lint seed build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	docker-compose exec backend pytest -v --cov=app --cov=scheduling --cov-report=term-missing

migrate:
	docker-compose exec backend alembic upgrade head

lint:
	docker-compose exec backend ruff check .

seed:
	docker-compose exec backend python -m app.seed

build:
	docker-compose build
