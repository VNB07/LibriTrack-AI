FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/ ./backend/
COPY ml/ ./ml/

RUN pip install --no-cache-dir -r backend/requirements.txt && \
    pip install --no-cache-dir --no-deps face_recognition==1.3.0

ENV PYTHONPATH=/app
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
