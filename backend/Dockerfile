# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Install the same pinned uv release used by CI. Installing the PyPI wheel keeps
# image builds independent of GHCR authentication while preserving lockfile sync.
RUN pip install --no-cache-dir --disable-pip-version-check uv==0.12.7

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
# Resolve the committed lock exactly and keep development tools out of production.
RUN uv sync --locked --no-dev --no-install-project

# Production stage
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Local OCR runtime is included for deployments that opt in with OCR_ENABLED.
# Keeping the switch off by default avoids OCR cost on standard PDF uploads.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=base /app/.venv /app/.venv

COPY . .

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
