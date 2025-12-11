# syntax=docker/dockerfile:1.7
# Multi-stage build for Python 3.12 trading application (2025)

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better layer caching
COPY requirements-core.txt requirements-ml.txt requirements-analysis.txt ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    -r requirements-core.txt \
    -r requirements-ml.txt \
    -r requirements-analysis.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash trader && \
    mkdir -p models data logs .benchmarks && \
    chown -R trader:trader /app

# Copy application code
COPY --chown=trader:trader . .

# Switch to non-root user
USER trader

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose dashboard port
EXPOSE 8080

# Default command
CMD ["python", "-m", "uvicorn", "src.api.dashboard:app", "--host", "0.0.0.0", "--port", "8080"]
