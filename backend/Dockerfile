FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

COPY --chown=app:app alembic.ini /app/alembic.ini
COPY --chown=app:app migrations /app/migrations
COPY --chown=app:app backend /app/backend
RUN mkdir -p /app/data && chown app:app /app/data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEVFLOW_INLINE_WORKERS_ENABLED=false \
    DEVFLOW_ENVIRONMENT=production \
    DEVFLOW_DOCS_ENABLED=false \
    DEVFLOW_AUTO_MIGRATE=false

USER app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
