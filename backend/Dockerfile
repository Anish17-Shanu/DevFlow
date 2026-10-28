FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=app:app backend /app/backend
RUN mkdir -p /app/data && chown app:app /app/data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEVFLOW_DATABASE_URL=sqlite+aiosqlite:////app/data/devflow.db \
    DEVFLOW_INLINE_WORKERS_ENABLED=false \
    DEVFLOW_ENVIRONMENT=production \
    DEVFLOW_DOCS_ENABLED=false

USER app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
