.PHONY: help install dev run test lint format clean

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Create virtual environment
	uv venv .venv

install: venv ## Install production dependencies
	uv pip install -e .

dev: venv ## Install with dev dependencies
	uv pip install -e ".[dev]"

full: venv ## Install with all optional dependencies
	uv pip install -e ".[dev,full]"

run: ## Start the Aegis server
	$(PYTHON) -m aegis

run-dev: ## Start with auto-reload
	.venv/bin/uvicorn aegis.app:create_app --factory --reload --host 127.0.0.1 --port 8000 --app-dir src

test: ## Run tests
	.venv/bin/pytest tests/ -v --cov=aegis --cov-report=term-missing

test-unit: ## Run unit tests only
	.venv/bin/pytest tests/unit/ -v

lint: ## Run linter
	.venv/bin/ruff check src/ tests/

format: ## Format code
	.venv/bin/ruff format src/ tests/
	.venv/bin/ruff check --fix src/ tests/

typecheck: ## Run type checker
	.venv/bin/mypy src/aegis/

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

db-reset: ## Reset the database
	rm -f data/aegis.db data/aegis.db-wal data/aegis.db-shm

web-install: ## Install frontend dependencies
	cd web && npm install

web-dev: ## Start frontend dev server
	cd web && node_modules/.bin/vite --host

web-build: ## Build frontend for production
	cd web && node_modules/.bin/vite build

dev-all: ## Start both backend and frontend
	@echo "Starting backend on :8000 and frontend on :5173..."
	@$(PYTHON) -m aegis & cd web && node_modules/.bin/vite --host

docker-up: ## Start full stack with Docker Compose
	LITELLM_BASE_URL=http://host.docker.internal:5000 docker compose up --build -d

docker-tunnel: ## Start full stack + Cloudflare Quick Tunnel (no setup needed)
	LITELLM_BASE_URL=http://host.docker.internal:5000 docker compose --profile tunnel up --build -d
	@echo ""
	@echo "Waiting for tunnel to come up..."
	@sleep 5
	@echo ""
	@echo "Public URL:"
	@docker compose logs tunnel 2>&1 | grep -o 'https://[^ ]*trycloudflare.com' | tail -1 || echo "Not ready yet — try: docker compose logs tunnel | grep trycloudflare.com"

docker-down: ## Stop Docker Compose stack
	docker compose --profile tunnel down

docker-reset: ## Reset Docker stack (wipe DB)
	docker compose down -v
	LITELLM_BASE_URL=http://host.docker.internal:5000 docker compose up --build -d

docker-logs: ## Show Docker Compose logs
	docker compose logs -f

tunnel: ## Expose local server via ngrok (run `make run` first)
	@echo "Starting ngrok tunnel to localhost:8000..."
	@echo "Your agent will be accessible from the internet."
	@echo ""
	python3 -c "\
	from pyngrok import ngrok; \
	tunnel = ngrok.connect(8000, 'http'); \
	print(f'Public URL: {tunnel.public_url}'); \
	print(f'Webhook base: {tunnel.public_url}/api/hooks/YOUR_SLUG'); \
	print(); \
	print('Press Ctrl+C to stop'); \
	import time; \
	[time.sleep(1) for _ in iter(int, 1)]"
