# Python 3.12 matches a widely available slim image for ECS/Fargate.
FROM python:3.12-slim

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
