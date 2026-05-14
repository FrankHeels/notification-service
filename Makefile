.PHONY: up down migrate migration test test-cov lint format typecheck \
        worker-email worker-telegram run clean

# ──────────────────────────────────────────
# Docker
# ──────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

# ──────────────────────────────────────────
# Миграции
# ──────────────────────────────────────────

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

# ──────────────────────────────────────────
# Тесты
# ──────────────────────────────────────────

test:
	pytest tests/

test-cov:
	pytest tests/ --cov=src --cov-report=term-missing

# ──────────────────────────────────────────
# Линтинг и форматирование
# ──────────────────────────────────────────

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	mypy src

# ──────────────────────────────────────────
# Воркеры
# ──────────────────────────────────────────

worker-email:
	python -m scripts.run_worker --channel email

worker-telegram:
	python -m scripts.run_worker --channel telegram


# ──────────────────────────────────────────
# Запуск всего проекта с нуля
# ──────────────────────────────────────────
run:
	docker compose up -d --build
	@echo "Application is running at http://localhost:8000"
	@echo "RabbitMQ UI at http://localhost:15672"
	@echo "Mailpit UI at http://localhost:8025"

clean:
	docker compose down -v
