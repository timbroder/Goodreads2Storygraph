# Phase 5: Integration & Deployment Testing Guide

## Overview

This document provides comprehensive testing procedures for Phase 5 of the Goodreads → StoryGraph sync service. These tests verify that the Docker container, cron scheduling, and data persistence all work correctly.

## Prerequisites

- Docker and Docker Compose installed
- `.env` file created from `.env.example` with valid credentials
- `data/` directory structure created (done automatically by entrypoint)

---

## Test 1: Cron Scheduling Inside Container

### Purpose
Verify that cron is properly configured and executes the sync job on schedule.

### Steps

#### 1.1 Build and Start Container

```bash
# Build the Docker image
docker compose build

# Start the container
docker compose up -d

# Verify container is running
docker ps | grep goodreads-sync
```

**Expected Output:**
- Container builds successfully without errors
- Container is running with status "Up"

#### 1.2 Verify Cron Installation

```bash
# Check that cron is running inside container
docker exec goodreads2storygraph-sync ps aux | grep cron

# View the installed crontab
docker exec goodreads2storygraph-sync crontab -l
```

**Expected Output:**
```
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
GOODREADS_EMAIL=***
GOODREADS_PASSWORD=***
STORYGRAPH_EMAIL=***
STORYGRAPH_PASSWORD=***
HEADLESS=true
LOG_LEVEL=INFO
TZ=America/New_York

0 3 * * * /app/sync_wrapper.sh
```

#### 1.3 Test Manual Execution

Before waiting for the scheduled run, test manual execution:

```bash
# Run sync manually to verify it works
docker exec goodreads2storygraph-sync python -m sync.main

# Check for errors
echo $?
```

**Expected Output:**
- Exit code 0 (success)
- Log messages showing sync progress
- CSV file created in `/data/artifacts/`

#### 1.4 Test Cron Execution with Rapid Schedule

To avoid waiting for the default 3 AM run, temporarily set a rapid schedule:

```bash
# Stop the container
docker compose down

# Edit .env to set a rapid schedule (every minute for testing)
# Add or update: CRON_SCHEDULE=* * * * *

# Restart container
docker compose up -d

# Watch the logs for cron execution
docker logs -f goodreads2storygraph-sync
```

**Expected Output:**
- Cron executes the sync job every minute
- Each execution logs start and completion
- Logs appear in both container output and `/data/logs/`

#### 1.5 Verify Cron Environment Variables

```bash
# Check that environment variables are properly passed to cron
docker exec goodreads2storygraph-sync sh -c 'crontab -l | grep -E "^(GOODREADS_|STORYGRAPH_|HEADLESS|LOG_LEVEL)"'
```

**Expected Output:**
- All required environment variables are present in crontab
- Values match those in `.env` file

#### 1.6 Check Cron Logs

```bash
# View container logs to see cron execution
docker logs --tail 50 goodreads2storygraph-sync

# Check syslog for cron entries (if available)
docker exec goodreads2storygraph-sync tail -f /var/log/syslog 2>/dev/null || echo "Syslog not available"
```

**Expected Output:**
- Container logs show cron starting: "Starting cron daemon..."
- Cron execution messages appear at scheduled times

---

## Test 2: Verify Artifacts and Logs in /data Volume

### Purpose
Ensure that all outputs (logs, CSVs, screenshots, state files) are properly persisted to the mounted `/data` volume.

### Steps

#### 2.1 Verify Directory Structure

```bash
# Check that all directories were created
ls -R ./data/

# Or use tree for better visualization
tree ./data/
```

**Expected Structure:**
```
./data/
├── logs/
│   ├── sync.log                          # Main log file
│   └── runs/
│       └── YYYYMMDD_HHMMSS.log          # Per-run logs
├── artifacts/
│   ├── goodreads_export_YYYYMMDD_HHMMSS.csv
│   ├── screenshots/
│   │   └── YYYYMMDD_HHMMSS/
│   │       └── *.png                     # Error screenshots
│   └── html/
│       └── YYYYMMDD_HHMMSS/
│           └── *.html                    # Error page HTML
└── state/
    ├── playwright_storage_goodreads.json
    ├── playwright_storage_storygraph.json
    └── last_sync_state.json
```

#### 2.2 Verify Log Files

```bash
# Check main log file exists and has content
cat ./data/logs/sync.log

# Check per-run logs
ls -lh ./data/logs/runs/

# View latest run log
cat ./data/logs/runs/$(ls -t ./data/logs/runs/ | head -1)
```

**Expected Output:**
- Main log file contains timestamped entries
- Per-run logs exist with timestamps in filename
- Logs include: start time, sync steps, completion time, exit code

#### 2.3 Verify Exported CSV

```bash
# List exported CSVs
ls -lh ./data/artifacts/goodreads_export_*.csv

# Check CSV has content
head -20 ./data/artifacts/$(ls -t ./data/artifacts/goodreads_export_*.csv | head -1)

# Count books in CSV
tail -n +2 ./data/artifacts/$(ls -t ./data/artifacts/goodreads_export_*.csv | head -1) | wc -l
```

**Expected Output:**
- CSV file exists with timestamp in filename
- CSV has header row and book data
- Book count matches your Goodreads library

#### 2.4 Verify State Files

```bash
# Check state files exist
ls -lh ./data/state/

# View last sync state
cat ./data/state/last_sync_state.json
```

**Expected Output:**
```json
{
  "last_hash": "sha256_hash_of_csv",
  "last_sync_timestamp": "2026-01-15T12:00:00Z",
  "last_book_count": 123
}
```

#### 2.5 Verify Session Persistence

```bash
# Check Playwright storage state files
ls -lh ./data/state/playwright_storage_*.json

# Verify they contain valid JSON
cat ./data/state/playwright_storage_goodreads.json | python -m json.tool > /dev/null && echo "Valid JSON"
cat ./data/state/playwright_storage_storygraph.json | python -m json.tool > /dev/null && echo "Valid JSON"
```

**Expected Output:**
- Both storage state JSON files exist
- Files are valid JSON
- Files contain cookies and localStorage data

#### 2.6 Test Data Persistence Across Restarts

```bash
# Note current file count
echo "Before restart:"
ls -R ./data/ | wc -l

# Restart container
docker compose restart

# Check files still exist
echo "After restart:"
ls -R ./data/ | wc -l

# Verify state file is still readable
cat ./data/state/last_sync_state.json
```

**Expected Output:**
- File count remains the same after restart
- All data persists across container restart
- State files are still valid

#### 2.7 Test Skip Logic

```bash
# Run sync twice without library changes
docker exec goodreads2storygraph-sync python -m sync.main
sleep 5
docker exec goodreads2storygraph-sync python -m sync.main

# Check logs for skip message
grep -i "skipping upload" ./data/logs/sync.log
```

**Expected Output:**
- First run: CSV uploaded
- Second run: "Library unchanged, skipping upload" message
- State file shows same hash on both runs

#### 2.8 Test Error Handling and Screenshots

To test error handling (requires intentionally breaking something):

```bash
# Run with invalid credentials or network issues
docker exec goodreads2storygraph-sync sh -c "GOODREADS_PASSWORD=wrong python -m sync.main" || true

# Check for error screenshot
ls -lh ./data/artifacts/screenshots/

# Check for error HTML
ls -lh ./data/artifacts/html/
```

**Expected Output:**
- Error screenshots saved when failures occur
- HTML snapshots captured for debugging
- Detailed error messages in logs

---

## Test 3: Integration Tests

### Purpose
Verify end-to-end functionality with various scenarios.

### 3.1 Full Sync Flow

```bash
# Clean state to force full sync
rm -f ./data/state/last_sync_state.json

# Run sync
docker exec goodreads2storygraph-sync python -m sync.main

# Verify all steps completed
tail -50 ./data/logs/sync.log
```

**Expected Output:**
1. Login to Goodreads
2. Export CSV
3. Calculate hash
4. Login to StoryGraph
5. Upload CSV
6. Verify success
7. Save state

### 3.2 Dry Run Mode

```bash
# Run in dry-run mode
docker exec goodreads2storygraph-sync sh -c "DRY_RUN=true python -m sync.main"

# Verify no upload occurred but export worked
grep -i "dry run" ./data/logs/sync.log
ls ./data/artifacts/goodreads_export_*.csv
```

**Expected Output:**
- CSV exported
- Upload skipped with "DRY_RUN mode" message
- No changes to StoryGraph

### 3.3 Force Full Sync

```bash
# Run normal sync
docker exec goodreads2storygraph-sync python -m sync.main

# Run with force flag (should upload even if unchanged)
docker exec goodreads2storygraph-sync sh -c "FORCE_FULL_SYNC=true python -m sync.main"

# Check logs
grep -i "force" ./data/logs/sync.log
```

**Expected Output:**
- Normal run: skips upload if unchanged
- Force run: uploads even if unchanged

### 3.4 Health Check

```bash
# Check container health status
docker inspect goodreads2storygraph-sync | grep -A 10 Health

# Manually run health check
docker exec goodreads2storygraph-sync test -f /data/logs/sync.log && echo "Healthy" || echo "Unhealthy"
```

**Expected Output:**
- Health status: "healthy"
- Log file exists

---

## Test 4: Cleanup and Maintenance

### 4.1 Log Rotation

```bash
# Check old logs are cleaned up (30+ days)
# Create test old log
touch -d "40 days ago" ./data/logs/runs/old_test.log

# Run cleanup (happens automatically in sync_wrapper.sh)
docker exec goodreads2storygraph-sync /app/sync_wrapper.sh

# Verify old log was deleted
ls ./data/logs/runs/old_test.log 2>&1
```

**Expected Output:**
- Old logs (30+ days) are automatically deleted

### 4.2 Container Resource Usage

```bash
# Check memory and CPU usage
docker stats goodreads2storygraph-sync --no-stream

# Check disk usage
docker exec goodreads2storygraph-sync du -sh /data/*
```

**Expected Output:**
- Memory usage: 500MB-1GB during sync, ~200MB idle
- CPU usage: Spike during sync, minimal idle
- Disk usage reasonable and growing slowly

---

## Test 5: Edge Cases and Error Scenarios

### 5.1 Missing Environment Variables

```bash
# Start container without required env vars (should fail)
docker run --rm -it \
  -v $(pwd)/data:/data \
  goodreads2storygraph-sync:latest

# Should exit with error message
```

**Expected Output:**
- Container exits immediately
- Error: "GOODREADS_EMAIL and GOODREADS_PASSWORD must be set"

### 5.2 Network Failures

```bash
# Disconnect network during sync
docker network disconnect bridge goodreads2storygraph-sync || true
docker exec goodreads2storygraph-sync python -m sync.main || true

# Reconnect
docker network connect bridge goodreads2storygraph-sync || true

# Check error handling
tail -50 ./data/logs/sync.log
```

**Expected Output:**
- Error logged with details
- Screenshot and HTML captured
- Exit code non-zero

### 5.3 Concurrent Execution Prevention

```bash
# Try running two syncs simultaneously
docker exec goodreads2storygraph-sync python -m sync.main &
docker exec goodreads2storygraph-sync python -m sync.main &
wait

# Check logs for conflicts
grep -i "lock\|already running" ./data/logs/sync.log
```

**Expected Behavior:**
- Should handle gracefully (may need lock mechanism)

---

## Success Criteria

All tests must pass for Phase 5 to be complete:

- ✅ Cron executes on schedule
- ✅ Logs written to `/data/logs/`
- ✅ CSVs exported to `/data/artifacts/`
- ✅ State persists in `/data/state/`
- ✅ Session cookies reused across runs
- ✅ Skip logic works (unchanged library)
- ✅ Error screenshots captured
- ✅ Container restarts without data loss
- ✅ Health checks pass
- ✅ Environment variables properly passed to cron

---

## Troubleshooting

### Cron Not Executing

1. Check cron is running: `docker exec goodreads2storygraph-sync ps aux | grep cron`
2. Verify crontab: `docker exec goodreads2storygraph-sync crontab -l`
3. Check container logs: `docker logs goodreads2storygraph-sync`
4. Verify timezone: `docker exec goodreads2storygraph-sync date`

### Logs Not Appearing

1. Check permissions: `ls -la ./data/logs/`
2. Check volume mount: `docker inspect goodreads2storygraph-sync | grep Mounts -A 10`
3. Run manual sync: `docker exec goodreads2storygraph-sync python -m sync.main`

### State Not Persisting

1. Verify state directory: `ls -la ./data/state/`
2. Check file contents: `cat ./data/state/last_sync_state.json`
3. Check for write errors: `docker logs goodreads2storygraph-sync | grep -i "state\|error"`

---

## Restoring Default Schedule

After rapid testing, restore the normal schedule:

```bash
# Stop container
docker compose down

# Edit .env to restore default schedule
# CRON_SCHEDULE=0 3 * * *

# Restart
docker compose up -d
```

---

## Conclusion

Once all tests pass, Phase 5 is complete and the service is ready for production use. Document any issues found and ensure they are resolved before finalizing the phase.
