FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY requirements.txt ./
# Upgrade pip first to avoid issues
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY --chown=appuser:appuser orchestrator ./orchestrator
COPY --chown=appuser:appuser agents ./agents
COPY --chown=appuser:appuser healthcheck_server.py ./
COPY --chown=appuser:appuser tests ./tests

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV PORT=8080
ENV RUN_BATCH_ON_START=false

# Create necessary directories for FinOps
RUN mkdir -p /app/logs /app/data /app/data/finops /app/data/finops/history && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check (FastAPIのヘルスチェックエンドポイントを使用)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE 8080

# Run the main FastAPI application instead of healthcheck_server.py
CMD ["python", "-m", "uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8080"]