# =============================================================================
# Makefile for Polymarket Liquidity Bot Docker Operations
# =============================================================================

.PHONY: help build up down logs restart clean test shell config

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE := docker compose
SERVICE_TRADING := trading-bot
SERVICE_MARKET := market-updater
SERVICE_STATS := stats-updater

## help: Show this help message
help:
	@echo "Polymarket Liquidity Bot - Docker Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make <target>"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  %-20s %s\n", $$1, $$2 } /^##@/ { printf "\n%s\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

## build: Build Docker images
build:
	@echo "Building Docker images..."
	$(COMPOSE) build --no-cache

## up: Start all services
up:
	@echo "Starting all services..."
	$(COMPOSE) up -d
	@echo "Services started. Use 'make logs' to view logs."

## down: Stop all services
down:
	@echo "Stopping all services..."
	$(COMPOSE) down

## restart: Restart all services
restart: down up

## logs: View logs (all services)
logs:
	$(COMPOSE) logs -f

## logs-trading: View trading bot logs
logs-trading:
	$(COMPOSE) logs -f $(SERVICE_TRADING)

## logs-market: View market updater logs
logs-market:
	$(COMPOSE) logs -f $(SERVICE_MARKET)

## logs-stats: View stats updater logs
logs-stats:
	$(COMPOSE) logs -f $(SERVICE_STATS)

## ps: Show running containers
ps:
	$(COMPOSE) ps

## shell: Open shell in trading bot container
shell:
	$(COMPOSE) exec $(SERVICE_TRADING) /bin/bash

## shell-trading: Open shell in trading bot
shell-trading:
	$(COMPOSE) exec $(SERVICE_TRADING) /bin/bash

## shell-market: Open shell in market updater
shell-market:
	$(COMPOSE) exec $(SERVICE_MARKET) /bin/bash

## config: Validate and print configuration
config:
	$(COMPOSE) exec $(SERVICE_TRADING) python config.py

## test: Run tests
test:
	$(COMPOSE) exec $(SERVICE_TRADING) python -m pytest

## clean: Remove containers, volumes, and images
clean:
	@echo "Cleaning up Docker resources..."
	$(COMPOSE) down -v --remove-orphans
	docker image rm polymarket-liquidity-bot_trading-bot 2>/dev/null || true
	@echo "Cleanup complete."

## prune: Clean up unused Docker resources
prune:
	@echo "Pruning unused Docker resources..."
	docker system prune -f
	docker volume prune -f

## health: Check health of all services
health:
	@echo "Checking service health..."
	@$(COMPOSE) ps --format json | jq -r '.[] | "\(.Service): \(.Health)"'

## restart-trading: Restart only trading bot
restart-trading:
	$(COMPOSE) restart $(SERVICE_TRADING)

## restart-market: Restart only market updater
restart-market:
	$(COMPOSE) restart $(SERVICE_MARKET)

## restart-stats: Restart only stats updater
restart-stats:
	$(COMPOSE) restart $(SERVICE_STATS)

## pull: Pull latest images
pull:
	$(COMPOSE) pull

## validate: Validate docker-compose.yml
validate:
	$(COMPOSE) config

## backup: Backup data and logs
backup:
	@echo "Creating backup..."
	@mkdir -p backups
	@tar -czf backups/backup-$$(date +%Y%m%d-%H%M%S).tar.gz logs/ data/ positions/ .env
	@echo "Backup created in backups/"

## init: Initialize setup (copy .env, create directories)
init:
	@echo "Initializing setup..."
	@if [ ! -f .env ]; then \
		cp .env.docker .env; \
		echo "Created .env from .env.docker"; \
		echo "⚠️  Please edit .env and add your credentials!"; \
	else \
		echo ".env already exists"; \
	fi
	@mkdir -p logs data positions
	@echo "✓ Directories created"
	@echo "✓ Initialization complete"
	@echo ""
	@echo "Next steps:"
	@echo "1. Edit .env and add your PK and BROWSER_ADDRESS"
	@echo "2. Place credentials.json in project root (if using Google Sheets write access)"
	@echo "3. Run 'make build' to build images"
	@echo "4. Run 'make up' to start services"

## dev: Start in development mode (logs visible)
dev:
	$(COMPOSE) up

## prod: Start in production mode (detached)
prod: up
	@echo "Production mode started. Services running in background."

## stop-trading: Stop only trading bot
stop-trading:
	$(COMPOSE) stop $(SERVICE_TRADING)

## stop-market: Stop only market updater
stop-market:
	$(COMPOSE) stop $(SERVICE_MARKET)

## stop-stats: Stop only stats updater
stop-stats:
	$(COMPOSE) stop $(SERVICE_STATS)
