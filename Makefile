.PHONY: help infra infra-down backend backend-no-reload frontend simulate test lint clean venv-help

# Prefer a repo-local venv so `make` does not use broken Homebrew Python (pyexpat /
# libexpat mismatch on some macOS setups). Create once with:
#   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
#   make setup
ifneq ($(wildcard $(CURDIR)/.venv/bin/python3),)
  PYTHON := $(CURDIR)/.venv/bin/python3
else
  PYTHON := python3
endif
PIP := $(PYTHON) -m pip
NPM := npm

# Backend dev server (override if port 8000 is busy: make backend BACKEND_PORT=8001)
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000

# ── Help ───────────────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ─────────────────────────────────────────────────────────────
infra: ## Start Redis, OTel Collector, Jaeger, Prometheus
	docker compose -f infra/docker-compose.yml up -d
	@echo ""
	@echo "  Redis      → localhost:6379"
	@echo "  Jaeger UI  → http://localhost:16686"
	@echo "  Prometheus → http://localhost:9090"
	@echo ""

infra-down: ## Stop all infra containers
	docker compose -f infra/docker-compose.yml down

infra-logs: ## Tail infra logs
	docker compose -f infra/docker-compose.yml logs -f

# ── Backend ────────────────────────────────────────────────────────────────────
backend-install: ## Install Python dependencies
	cd backend && $(PIP) install -r requirements.txt

backend: ## Start FastAPI backend (hot-reload)
	@cd $(CURDIR) && $(PYTHON) -m uvicorn backend.api.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload-dir backend

backend-no-reload: ## Same as backend but without --reload (use if you hit EADDRINUSE / errno 48)
	@cd $(CURDIR) && $(PYTHON) -m uvicorn backend.api.main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT)

backend-mcp: ## Start MCP server standalone (for testing tools)
	cd backend && $(PYTHON) -m mcp.server

# ── Frontend ───────────────────────────────────────────────────────────────────
frontend-install: ## Install Node dependencies
	cd frontend && $(NPM) install

frontend: ## Start React dev server (Vite proxy → BACKEND_PORT, same as make backend)
	cd frontend && DEVMIND_BACKEND_PORT=$(BACKEND_PORT) $(NPM) run dev

frontend-build: ## Build React for production
	cd frontend && $(NPM) run build

# ── Combined Dev ───────────────────────────────────────────────────────────────
dev: infra ## Start everything for local development (infra + backend + frontend)
	@echo "Starting backend and frontend in parallel..."
	@$(MAKE) -j2 backend frontend

venv-help: ## Show how to create .venv when Homebrew Python breaks (pyexpat error)
	@echo "If pip fails with pyexpat / libexpat / XML_SetAllocTrackerActivationThreshold:"
	@echo "  Use Python from python.org or a working interpreter, then:"
	@echo "  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv"
	@echo "  make setup"

setup: ## First-time setup: install all dependencies
	@echo "Installing backend dependencies..."
	$(MAKE) backend-install
	@echo "Installing frontend dependencies..."
	$(MAKE) frontend-install
	@echo ""
	@echo "  Next steps:"
	@echo "  1. cp backend/.env.example backend/.env"
	@echo "  2. Fill in ANTHROPIC_API_KEY and GITHUB_TOKEN"
	@echo "  3. make dev"

# ── Simulation ─────────────────────────────────────────────────────────────────
simulate: ## Run full simulation: generate 500 PRs → run agent → print metrics
	@echo "Generating 500 synthetic PRs..."
	cd simulation && $(PYTHON) generate_prs.py --count 500 --output data/prs.jsonl --seed 42
	@echo "Running simulation (cached)..."
	cd simulation && $(PYTHON) run_simulation.py --input data/prs.jsonl \
		--output data/results.jsonl --mock-claude
	@echo "Running simulation (no cache, for baseline)..."
	cd simulation && $(PYTHON) run_simulation.py --input data/prs.jsonl \
		--output data/results_nocache.jsonl --mock-claude --no-cache
	@echo "Computing metrics..."
	cd simulation && $(PYTHON) report.py \
		--results data/results.jsonl \
		--baseline data/results_nocache.jsonl

simulate-quick: ## Quick simulation with 50 PRs
	cd simulation && $(PYTHON) generate_prs.py --count 50 --output data/prs_quick.jsonl
	cd simulation && $(PYTHON) run_simulation.py --input data/prs_quick.jsonl \
		--output data/results_quick.jsonl --mock-claude
	cd simulation && $(PYTHON) report.py --results data/results_quick.jsonl

# ── Tests ──────────────────────────────────────────────────────────────────────
test: ## Run unit tests
	cd backend && $(PYTHON) -m pytest tests/unit -v

test-watch: ## Run tests in watch mode
	cd backend && $(PYTHON) -m pytest tests/unit -v --tb=short -f

test-cov: ## Run tests with coverage report
	cd backend && $(PYTHON) -m pytest tests/unit \
		--cov=. --cov-report=term-missing --cov-report=html

# ── Linting ────────────────────────────────────────────────────────────────────
lint: ## Lint backend Python code
	cd backend && $(PYTHON) -m ruff check . && $(PYTHON) -m mypy . --ignore-missing-imports

lint-fix: ## Auto-fix lint issues
	cd backend && $(PYTHON) -m ruff check . --fix

# ── Tunnel ─────────────────────────────────────────────────────────────────────
tunnel: ## Expose local BACKEND_PORT (default 8000) via ngrok
	@echo "Starting ngrok tunnel on port $(BACKEND_PORT)..."
	@echo "Copy the HTTPS URL and set it as your GitHub webhook URL."
	ngrok http $(BACKEND_PORT)

# ── Utilities ──────────────────────────────────────────────────────────────────
env-check: ## Verify required environment variables are set
	@$(PYTHON) -c "\
import os, sys; \
required = ['ANTHROPIC_API_KEY', 'GITHUB_TOKEN']; \
missing = [v for v in required if not os.getenv(v)]; \
[print(f'  ❌ Missing: {v}') for v in missing] or print('  ✅ All required env vars set'); \
sys.exit(len(missing))"

clean: ## Remove generated simulation data and caches
	rm -rf simulation/data/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
