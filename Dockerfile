# Production Dockerfile for DigitalOcean App Platform & Droplets
FROM python:3.11-slim

# System dependencies for git repos and testing
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure directory structure
RUN mkdir -p /app/capsule_output/intermediate \
    && mkdir -p /app/dependency-exit-capsule/target

# DigitalOcean App Platform port
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "app.py"]
