# Dockerfile untuk Backend Container
# ====================================

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Copy backend entrypoint
COPY docker/backend/entrypoint.py .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run backend
CMD ["python", "entrypoint.py"]
