FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Make the backend package importable
ENV PYTHONPATH=/app

CMD ["python", "-m", "backend.queue.worker_entrypoint"]
