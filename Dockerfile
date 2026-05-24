# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.16 AS uv

FROM node:22-bookworm-slim AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY tailwind.config.js ./
COPY static/css/tailwind-src.css ./static/css/tailwind-src.css
COPY templates ./templates
COPY static/js ./static/js
RUN npm run build:css

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
COPY static ./static
COPY --from=assets /build/static/css/tailwind.css ./static/css/tailwind.css
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
COPY static ./static
COPY --from=assets /build/static/css/tailwind.css ./static/css/tailwind.css
RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser
EXPOSE 8000
# `--forwarded-allow-ips "*"` makes uvicorn honour `X-Forwarded-Proto` from
# fly-proxy (its default trusts only 127.0.0.1, which fly-proxy is not). Without
# this `request.base_url` reports `http://...` for HTTPS visitors, every
# absolute URL we render is mis-schemed, and htmx 2.x refuses cross-origin
# (mixed-scheme) requests with `htmx:invalidPath`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
