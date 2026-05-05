# Debian Trixie slim image (Python 3.14).

# Test image: pytest + dev deps (CI and `docker compose --profile test run test`).
FROM python:3.14-slim-trixie AS test

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY tests ./tests

ENV PYTHONUNBUFFERED=1

CMD ["pytest"]

# Production image (default stage for `docker build` with no --target).
FROM python:3.14-slim-trixie AS production

WORKDIR /app

RUN useradd --create-home --system --shell /usr/sbin/nologin appuser

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-prod.txt

COPY app ./app
COPY templates ./templates

# Writable SQLite path inside the container (mount a volume at /data on ECS).
ENV DND_SCHEDULER_DB_URL=sqlite:////data/dnd_scheduler.sqlite3

RUN mkdir -p /data && chown appuser /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
