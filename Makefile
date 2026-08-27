.DEFAULT_GOAL := help
COMPOSE ?= docker compose

.PHONY: help up down build logs rebuild test dev-api smoke

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Build both images
	$(COMPOSE) build

up: ## Start the stack (UI on http://localhost:$${WEB_PORT:-8080})
	$(COMPOSE) up -d
	@echo "UI:   http://localhost:$${WEB_PORT:-8080}"
	@echo "Docs: http://localhost:$${WEB_PORT:-8080}/api/docs"

down: ## Stop the stack
	$(COMPOSE) down

rebuild: ## Rebuild from scratch and restart
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --force-recreate

logs: ## Follow logs
	$(COMPOSE) logs -f

test: ## Run the test suite inside the api image
	$(COMPOSE) run --rm --entrypoint sh api -c \
	  "pip install --no-cache-dir pytest==8.3.4 >/dev/null && python -m pytest -q"

dev-api: ## Run the API locally with reload (needs a local venv)
	cd api && PYTHONPATH=src uvicorn moexcharts.main:app --reload --port 8000

smoke: ## Check that iss.moex.com is reachable from inside the api container
	$(COMPOSE) exec api python -m moexcharts.smoke
