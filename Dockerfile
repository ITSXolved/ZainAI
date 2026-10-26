# ── ZainAI 3D Conference Server Dockerfile ─────────────────────────────────────
# Optimized for Google Cloud Run, Docker Compose, and Containerized Deployments
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing bytecode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# Install minimal OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-docker.txt

# Copy application assets and codebase
COPY web/ ./web/
COPY avatar/ ./avatar/
COPY core/ ./core/
COPY actions/ ./actions/
COPY memory/ ./memory/
COPY providers/ ./providers/
COPY config/ ./config/
COPY headless_server.py .

# Healthcheck to verify FastAPI responds on PORT
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

EXPOSE 8080

CMD ["python", "headless_server.py"]
