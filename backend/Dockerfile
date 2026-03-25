FROM python:3.12-slim AS backend

WORKDIR /app

# System deps: curl is required by docker-compose healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Install backend and AI dependencies in one layer with no pip cache.
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY ai_models/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/ai-requirements.txt

# Copy project sources used by backend runtime.
COPY ai_models/ ./ai_models/
COPY backend/ ./backend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
