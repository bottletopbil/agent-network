# Multi-stage build for Agent
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
COPY --chown=swarm:swarm agents/ ./agents/

USER swarm

# Health check (agents don't have HTTP endpoint, check process)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python.*agents" || exit 1

# Expose metrics port (if agents expose metrics)
EXPOSE 8001

# Default to running planner agent (override with CMD in k8s)
CMD ["python", "agents/planner.py"]
