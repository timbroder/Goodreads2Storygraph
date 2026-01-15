#!/bin/bash
set -e

echo "=================================================="
echo "Goodreads → StoryGraph Sync Service"
echo "=================================================="

# Set timezone
if [ -n "$TZ" ]; then
    echo "Setting timezone to: $TZ"
    export TZ
else
    echo "Using default timezone: America/New_York"
    export TZ=America/New_York
fi

# Validate required environment variables
if [ -z "$GOODREADS_EMAIL" ] || [ -z "$GOODREADS_PASSWORD" ]; then
    echo "ERROR: GOODREADS_EMAIL and GOODREADS_PASSWORD must be set"
    exit 1
fi

if [ -z "$STORYGRAPH_EMAIL" ] || [ -z "$STORYGRAPH_PASSWORD" ]; then
    echo "ERROR: STORYGRAPH_EMAIL and STORYGRAPH_PASSWORD must be set"
    exit 1
fi

# Validate /data mount
if [ ! -d "/data" ]; then
    echo "ERROR: /data volume is not mounted"
    exit 1
fi

# Ensure directory structure exists
mkdir -p /data/logs/runs \
    /data/artifacts/screenshots \
    /data/artifacts/html \
    /data/state

# Set default cron schedule if not provided
CRON_SCHEDULE="${CRON_SCHEDULE:-0 3 * * *}"

echo "Configuring cron schedule: $CRON_SCHEDULE"

# Create crontab from template
sed "s|{{CRON_SCHEDULE}}|$CRON_SCHEDULE|g" /app/crontab.template > /tmp/crontab.txt

# Add environment variables to crontab
{
    echo "SHELL=/bin/bash"
    echo "PATH=/usr/local/bin:/usr/bin:/bin"
    echo "GOODREADS_EMAIL=$GOODREADS_EMAIL"
    echo "GOODREADS_PASSWORD=$GOODREADS_PASSWORD"
    echo "STORYGRAPH_EMAIL=$STORYGRAPH_EMAIL"
    echo "STORYGRAPH_PASSWORD=$STORYGRAPH_PASSWORD"
    echo "HEADLESS=${HEADLESS:-true}"
    echo "LOG_LEVEL=${LOG_LEVEL:-INFO}"
    echo "TZ=$TZ"
    [ -n "$MAX_SYNC_ITEMS" ] && echo "MAX_SYNC_ITEMS=$MAX_SYNC_ITEMS"
    [ -n "$DRY_RUN" ] && echo "DRY_RUN=$DRY_RUN"
    [ -n "$FORCE_FULL_SYNC" ] && echo "FORCE_FULL_SYNC=$FORCE_FULL_SYNC"
    echo ""
    cat /tmp/crontab.txt
} > /tmp/final_crontab.txt

# Install crontab for current user
crontab /tmp/final_crontab.txt

echo "Crontab installed successfully:"
crontab -l

echo "=================================================="
echo "Service initialization complete"
echo "Logs will be written to: /data/logs/"
echo "Next scheduled run: $(date -d "$(echo $CRON_SCHEDULE | awk '{print $2":"$1}')" '+%Y-%m-%d %H:%M' 2>/dev/null || echo 'See crontab schedule')"
echo "=================================================="

# Run initial sync if INITIAL_SYNC is set
if [ "$INITIAL_SYNC" = "true" ]; then
    echo "Running initial sync..."
    /app/sync_wrapper.sh
fi

# Start cron in foreground
echo "Starting cron daemon..."
exec cron -f
