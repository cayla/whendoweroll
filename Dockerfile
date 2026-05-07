# syntax=docker/dockerfile:1

# Debian Trixie slim image (Python 3.14).

FROM ghcr.io/astral-sh/uv:0.11.9 AS uv

# Test image: pytest + dev deps (CI and `docker compose --profile test run test`).
FROM python:3.14-slim-trixie AS test

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --group dev

COPY app ./app
COPY templates ./templates
COPY tests ./tests

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

CMD ["pytest"]

# Production image (default stage for `docker build` with no --target).
FROM python:3.14-slim-trixie AS production

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy

RUN useradd --create-home --system --shell /usr/sbin/nologin appuser

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

COPY app ./app
COPY templates ./templates

# Writable SQLite path inside the container (mount a volume at /data on ECS).
ENV WHENDOWEROLL_DB_URL=sqlite:////data/whendoweroll.sqlite3

RUN mkdir -p /data && chown -R appuser:appuser /data /app

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
