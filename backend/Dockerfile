FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend

ENV DEVFLOW_DATABASE_URL=sqlite+aiosqlite:////app/devflow.db
ENV DEVFLOW_INLINE_WORKERS_ENABLED=true

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
