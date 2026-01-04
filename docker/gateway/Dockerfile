# Dockerfile untuk Gateway/TPM Container
# ========================================

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Copy gateway entrypoint
COPY docker/gateway/entrypoint.py .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run gateway
CMD ["python", "entrypoint.py"]
