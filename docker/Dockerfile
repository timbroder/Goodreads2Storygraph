FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY ../requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chromium only to keep image size down)
RUN playwright install chromium --with-deps

# Create directory structure for data volume
RUN mkdir -p /data/logs/runs \
    /data/artifacts/screenshots \
    /data/artifacts/html \
    /data/state

# Copy application code
COPY ../sync /app/sync

# Copy Docker-specific files
COPY entrypoint.sh /app/entrypoint.sh
COPY crontab /app/crontab.template
COPY sync_wrapper.sh /app/sync_wrapper.sh

# Make scripts executable
RUN chmod +x /app/entrypoint.sh /app/sync_wrapper.sh

# Create non-root user for running the application
RUN useradd -m -u 1000 syncuser && \
    chown -R syncuser:syncuser /app /data

# Switch to non-root user
USER syncuser

# Set environment defaults
ENV HEADLESS=true \
    LOG_LEVEL=INFO \
    TZ=America/New_York \
    CRON_SCHEDULE="0 3 * * *"

# Volume for persistent data
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD test -f /data/logs/sync.log || exit 1

# Start cron via entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
