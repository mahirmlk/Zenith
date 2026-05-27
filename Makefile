.PHONY: dev backend frontend test lint format

# Start both frontend and backend in development mode
dev:
	docker compose up --build

# Backend only
backend:
	cd backend && uvicorn main:app --reload --port 8000

# Frontend only
frontend:
	cd frontend && npm run dev

# Run all tests
test:
	cd backend && pytest
	cd frontend && npm test

# Lint backend
lint-backend:
	cd backend && ruff check . && mypy .

# Lint frontend
lint-frontend:
	cd frontend && npm run lint

# Format backend
format-backend:
	cd backend && ruff check . --fix

# Install dependencies
install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install
