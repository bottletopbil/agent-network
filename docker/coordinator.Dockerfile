# Multi-stage build for Coordinator
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user first
RUN useradd -m -u 1000 swarm

# Copy Python dependencies from builder to swarm's home
COPY --from=builder --chown=swarm:swarm /root/.local /home/swarm/.local

# Make sure scripts in .local are usable
ENV PATH=/home/swarm/.local/bin:$PATH

# Copy application code
COPY --chown=swarm:swarm src/ ./src/

USER swarm

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Expose metrics port
EXPOSE 8000

# Run coordinator
CMD ["python", "src/coordinator.py"]
