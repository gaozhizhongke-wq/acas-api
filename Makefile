# ACAS v2 - Makefile
# Convenience commands for development and deployment

.PHONY: help install test coverage lint security docker-build docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -r requirements.txt

test: ## Run tests (exclude ML benchmarks that need torch)
	PYTHONPATH=src pytest tests/ -v --tb=short -q \
		-k "not benchmark and not TestTimesFMEngine and not TestForecastIntegration"

test-full: ## Run all tests
	PYTHONPATH=src pytest tests/ -v --tb=short

coverage: ## Run tests with coverage report
	PYTHONPATH=src pytest tests/ --cov=src --cov-report=term-missing \
		-k "not benchmark and not TestTimesFMEngine and not TestForecastIntegration"

lint: ## Run Ruff linter
	ruff check src/ tests/

security: ## Run Bandit security scan
	bandit -r src/

docker-build: ## Build Docker image
	docker build -t acas-api:latest .

docker-up: ## Start all services (development)
	docker compose up -d

docker-up-monitoring: ## Start all services with monitoring stack
	docker compose --profile monitoring up -d

docker-down: ## Stop all services
	docker compose down

clean: ## Clean cache and temporary files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml htmlcov/

db-upgrade: ## Run Alembic migrations
	PYTHONPATH=src alembic upgrade head

db-history: ## Show Alembic migration history
	PYTHONPATH=src alembic history

db-current: ## Show current Alembic revision
	PYTHONPATH=src alembic current
