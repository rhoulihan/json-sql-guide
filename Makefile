# json-sql-guide — make targets
.PHONY: help setup install test test-unit test-integration lint format typecheck clean db-up db-down db-logs catalog annotate run diff

help:
	@echo "json-sql-guide targets:"
	@echo "  setup             - bootstrap venv with uv, install deps, install pre-commit hooks"
	@echo "  install           - install package in editable mode"
	@echo "  test              - run unit + integration test suites"
	@echo "  test-unit         - run unit suite (no DB)"
	@echo "  test-integration  - run integration suite (requires Oracle container)"
	@echo "  lint              - ruff check"
	@echo "  format            - ruff format"
	@echo "  typecheck         - mypy strict"
	@echo "  db-up             - bring Oracle 26ai Free up via docker compose"
	@echo "  db-down           - stop and remove the DB container"
	@echo "  db-logs           - tail DB logs"
	@echo "  catalog           - extract SQL catalog from a guide markdown (SOURCE=...)"
	@echo "  annotate          - alias for run; writes annotated guide to reports/"
	@echo "  run               - run validator end-to-end (SOURCE=path/to/guide.md)"
	@echo "  diff              - diff two results.json files (PREV=... CURR=...)"
	@echo "  clean             - wipe venv, caches, build artifacts"

setup:
	uv venv
	uv pip install -e ".[dev]"
	uv run pre-commit install

install:
	uv pip install -e ".[dev]"

test: test-unit test-integration

test-unit:
	uv run pytest tests/unit -v --cov=validator --cov-fail-under=90

test-integration:
	uv run pytest tests/integration -v -m requires_oracle

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src tests

db-up:
	docker compose up -d
	@echo "waiting for Oracle to be healthy..."
	@until docker compose ps | grep -q "healthy"; do sleep 5; done
	@echo "Oracle 26ai Free is ready"

db-down:
	docker compose down -v

db-logs:
	docker compose logs -f oracle

catalog:
	@test -n "$(SOURCE)" || (echo "Usage: make catalog SOURCE=path/to/guide.md" && exit 1)
	uv run validator extract "$(SOURCE)" -o catalog.json

annotate: run

run:
	@test -n "$(SOURCE)" || (echo "Usage: make run SOURCE=path/to/guide.md" && exit 1)
	uv run validator run "$(SOURCE)" --out reports/

diff:
	@test -n "$(PREV)" || (echo "Usage: make diff PREV=path/to/prev.json CURR=path/to/curr.json" && exit 1)
	@test -n "$(CURR)" || (echo "Usage: make diff PREV=path/to/prev.json CURR=path/to/curr.json" && exit 1)
	uv run validator diff "$(PREV)" "$(CURR)" --format md

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
	rm -rf build dist *.egg-info
	rm -rf reports/
	find . -type d -name __pycache__ -exec rm -rf {} +
