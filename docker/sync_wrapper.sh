#!/bin/bash
# Wrapper script for cron execution of sync job
# Handles logging and error capture

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_LOG="/data/logs/runs/${TIMESTAMP}.log"

# Ensure logs directory exists
mkdir -p /data/logs/runs

# Log start time
echo "========================================" | tee -a "$RUN_LOG"
echo "Sync Job Started: $(date)" | tee -a "$RUN_LOG"
echo "========================================" | tee -a "$RUN_LOG"

# Change to app directory
cd /app || {
    echo "ERROR: Failed to change to /app directory" | tee -a "$RUN_LOG"
    exit 1
}

# Run the sync with full output capture
python -m sync.main 2>&1 | tee -a "$RUN_LOG" /data/logs/sync.log

EXIT_CODE=${PIPESTATUS[0]}

# Log completion
echo "========================================" | tee -a "$RUN_LOG"
echo "Sync Job Completed: $(date)" | tee -a "$RUN_LOG"
echo "Exit Code: $EXIT_CODE" | tee -a "$RUN_LOG"
echo "========================================" | tee -a "$RUN_LOG"

# Cleanup old run logs (keep last 30 days)
find /data/logs/runs -type f -name "*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
