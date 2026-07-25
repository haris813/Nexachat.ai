.PHONY: install run test lint typecheck security verify validate migrate cleanup-dry-run docker-up docker-down observability-up observability-down

install:
	python -m pip install -r requirements-dev.txt

run:
	python app.py

test:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy app scripts

security:
	bandit -q -r app
	pip-audit -r requirements.txt

migrate:
	flask --app app.py db upgrade

validate:
	python scripts/validate_repo.py

cleanup-dry-run:
	python -m scripts.cleanup_retention

verify: lint typecheck test
	python -m compileall -q app scripts tests app.py wsgi.py
	node --check static/js/app.js
	python scripts/validate_repo.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

observability-up:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build

observability-down:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down
