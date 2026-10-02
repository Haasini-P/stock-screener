FROM python:3.11-slim

WORKDIR /app

# System dependencies — libgomp1 is the OpenMP runtime LightGBM's Linux wheel
# dynamically links against; without it, `import lightgbm` fails at container
# runtime with "libgomp.so.1: cannot open shared object file" (the macOS
# equivalent of this, libomp via Homebrew, is already noted in requirements.txt).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Kubernetes uses its own httpGet probes (see k8s/backend.yaml) — this is for
# plain `docker run`/docker-compose, where nothing else watches container health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
