# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.9 AS uv

# Test image: pytest + dev deps (CI and `docker compose --profile test run test`).
FROM python:3.14-slim-trixie AS test
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --group dev
COPY app ./app
COPY templates ./templates
COPY tests ./tests
CMD ["pytest"]

# Production image (default stage for `docker build` with no --target).
FROM python:3.14-slim-trixie AS production
ENV UV_LINK_MODE=copy
ENV WHENDOWEROLL_DB_URL=sqlite:////data/whendoweroll.sqlite3
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
RUN useradd --create-home --system --uid 1000 --shell /usr/sbin/nologin appuser
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
COPY app ./app
COPY templates ./templates
RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
