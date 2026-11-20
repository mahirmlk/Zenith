.PHONY: dev backend frontend test lint lint-backend lint-frontend format format-backend install

# Start both frontend and backend in development mode
dev:
	docker compose up --build

# Backend only
backend:
	cd backend && uv run --locked uvicorn main:app --reload --port 8000

# Frontend only
frontend:
	cd frontend && npm run dev

# Run all tests
test:
	cd backend && uv run --locked pytest
	cd frontend && npm test

# Run backend and frontend lint/type checks
lint: lint-backend lint-frontend

# Lint backend
lint-backend:
	cd backend && uv run --locked ruff check . && uv run --locked mypy .

# Lint frontend
lint-frontend:
	cd frontend && npm run lint && npm run typecheck

# Format backend
format-backend:
	cd backend && uv run --locked ruff check . --fix && uv run --locked ruff format .

# Format Python backend files
format: format-backend

# Install dependencies
install:
	cd backend && uv sync --locked --extra dev
	cd frontend && npm ci
