# Goodreads → StoryGraph Sync Service - Detailed Documentation

## 📖 Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Volume Structure](#volume-structure)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Known Limitations](#known-limitations)
- [FAQ](#faq)

---

## Overview

This service automatically syncs your Goodreads library to TheStoryGraph using browser automation. It runs on a configurable schedule (default: daily at 3 AM) and intelligently skips uploads when your library hasn't changed.

### Key Features
- ✅ **Automated scheduling** - Set-it-and-forget-it cron-based syncing
- ✅ **Smart skip logic** - Compares CSV hash to avoid redundant uploads
- ✅ **Session persistence** - Reuses browser sessions to avoid frequent logins
- ✅ **Comprehensive logging** - Per-run logs with screenshots on failures
- ✅ **Docker-based** - Isolated environment with all dependencies included
- ✅ **Dry run mode** - Test without affecting your StoryGraph library
- ✅ **No transformation** - Uploads raw Goodreads CSV (StoryGraph handles deduplication)

---

## Prerequisites

- Docker and Docker Compose installed
- Active Goodreads account with books in your library
- Active StoryGraph account
- **Important**: Both accounts must NOT have 2FA/MFA enabled (automation limitation)

---

## Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd Goodreads2Storygraph
```

### 2. Configure environment variables
```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

Fill in your credentials:
```bash
GOODREADS_EMAIL=your-email@example.com
GOODREADS_PASSWORD=your-password
STORYGRAPH_EMAIL=your-email@example.com
STORYGRAPH_PASSWORD=your-password
```

### 3. Create data directory
```bash
mkdir -p data/{logs/runs,artifacts/screenshots,artifacts/html,state}
```

### 4. Build and start the container
```bash
docker compose up -d
```

---

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GOODREADS_EMAIL` | Your Goodreads login email | `user@example.com` |
| `GOODREADS_PASSWORD` | Your Goodreads password | `your-password` |
| `STORYGRAPH_EMAIL` | Your StoryGraph login email | `user@example.com` |
| `STORYGRAPH_PASSWORD` | Your StoryGraph password | `your-password` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SCHEDULE` | `0 3 * * *` | Cron expression for sync schedule |
| `TZ` | `America/New_York` | Timezone for scheduling |
| `HEADLESS` | `true` | Run browser in headless mode |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `MAX_SYNC_ITEMS` | (no limit) | Maximum books to sync (for testing) |
| `DRY_RUN` | `false` | Export but don't upload (testing mode) |
| `FORCE_FULL_SYNC` | `false` | Force upload even if CSV unchanged |

### Cron Schedule Examples

```bash
# Daily at 3 AM
CRON_SCHEDULE=0 3 * * *

# Every 6 hours
CRON_SCHEDULE=0 */6 * * *

# Every Sunday at midnight
CRON_SCHEDULE=0 0 * * 0

# Twice daily (6 AM and 6 PM)
CRON_SCHEDULE=0 6,18 * * *
```

---

## Usage

### Running the Sync Manually

Execute a sync immediately (useful for testing):
```bash
docker exec goodreads-sync python -m sync.main
```

### Viewing Logs

**Real-time logs:**
```bash
docker logs -f goodreads-sync
```

**Main log file:**
```bash
tail -f data/logs/sync.log
```

**Per-run logs:**
```bash
ls -ltr data/logs/runs/
cat data/logs/runs/2026-01-15_030000.log
```

### Testing with Dry Run

Test the export process without uploading:
```bash
docker exec goodreads-sync sh -c "DRY_RUN=true python -m sync.main"
```

### Force Full Sync

Force upload even if library unchanged:
```bash
docker exec goodreads-sync sh -c "FORCE_FULL_SYNC=true python -m sync.main"
```

### Checking Container Status

```bash
# View running containers
docker ps

# Check if cron is running
docker exec goodreads-sync ps aux | grep cron

# View crontab
docker exec goodreads-sync crontab -l
```

### Stopping the Service

```bash
docker compose down
```

### Restarting the Service

```bash
docker compose restart
```

---

## How It Works

### Sync Workflow

1. **Initialize** - Start Playwright browser (Chromium)
2. **Export from Goodreads**
   - Login (or reuse session from storage state)
   - Navigate to export page
   - Trigger CSV download
   - Save to `/data/artifacts/goodreads_export_<timestamp>.csv`
3. **Calculate Hash** - SHA256 hash of CSV content
4. **Compare State** - Check if hash matches last sync
5. **Smart Skip Decision**
   - If unchanged AND not forced → Skip upload
   - If changed OR forced → Proceed to upload
6. **Upload to StoryGraph** (if not skipped)
   - Login (or reuse session from storage state)
   - Navigate to import page
   - Upload CSV file
   - Wait for success confirmation
7. **Update State** - Save new hash, timestamp, and book count
8. **Cleanup** - Close browser and cleanup resources

### Smart Skip Logic

The sync service maintains state in `/data/state/last_sync_state.json`:
```json
{
  "last_hash": "a1b2c3...",
  "last_sync_timestamp": "2026-01-15T03:00:00",
  "last_book_count": 247
}
```

On each run:
- Calculate hash of current Goodreads export
- Compare with `last_hash`
- Skip upload if unchanged (unless `FORCE_FULL_SYNC=true`)

This prevents unnecessary uploads and respects rate limits.

### Session Persistence

Browser sessions are saved to:
- `/data/state/playwright_storage_goodreads.json`
- `/data/state/playwright_storage_storygraph.json`

Benefits:
- Avoids login on every run
- Reduces CAPTCHA risk
- Faster execution
- Sessions auto-refresh when expired

---

## Volume Structure

The `/data` directory contains all persistent data:

```
data/
├── logs/
│   ├── sync.log                          # Main rotating log
│   └── runs/
│       └── 2026-01-15_030000.log         # Per-run detailed logs
├── artifacts/
│   ├── goodreads_export_20260115_030000.csv  # Downloaded CSVs
│   ├── screenshots/                       # Error screenshots
│   │   └── 20260115_030000/
│   │       ├── goodreads_login_failed.png
│   │       └── storygraph_upload_error.png
│   └── html/                             # Error page HTML
│       └── 20260115_030000/
│           └── error_page.html
└── state/
    ├── playwright_storage_goodreads.json  # Session cookies
    ├── playwright_storage_storygraph.json # Session cookies
    └── last_sync_state.json               # Hash + metadata
```

---

## Troubleshooting

### Common Issues

#### 1. Login Failures

**Symptoms**: Logs show "Login failed" or "Could not verify login"

**Solutions**:
- Verify credentials in `.env` file
- Check if 2FA is disabled on both accounts
- Delete storage state files to force fresh login:
  ```bash
  rm data/state/playwright_storage_*.json
  ```
- Run in non-headless mode to see what's happening:
  ```bash
  docker exec goodreads-sync sh -c "HEADLESS=false python -m sync.main"
  ```

#### 2. CAPTCHA Challenges

**Symptoms**: Sync hangs or fails with timeout

**Solutions**:
- Login manually to your accounts from your browser first
- Wait 24 hours before retrying (reduce frequency temporarily)
- Check screenshots in `data/artifacts/screenshots/` for CAPTCHA detection
- Consider running less frequently (e.g., weekly instead of daily)

#### 3. Selector Not Found Errors

**Symptoms**: "Could not find element" or "Selector timed out"

**Possible Causes**:
- Goodreads or StoryGraph changed their UI
- Slow internet connection

**Solutions**:
- Check `sync/selectors.py` and update selectors if needed
- Increase browser timeout (see Advanced Configuration)
- Check the HTML dumps in `data/artifacts/html/` for page structure changes

#### 4. Container Not Syncing

**Symptoms**: No logs appearing, cron not running

**Solutions**:
```bash
# Check container is running
docker ps | grep goodreads-sync

# Check cron is running inside container
docker exec goodreads-sync ps aux | grep cron

# Check crontab is configured
docker exec goodreads-sync crontab -l

# Restart container
docker compose restart
```

#### 5. Permission Errors

**Symptoms**: "Permission denied" when accessing `/data`

**Solutions**:
```bash
# Fix ownership of data directory
sudo chown -R $(id -u):$(id -g) data/

# Or run container as root (not recommended)
docker compose run --user root goodreads-sync python -m sync.main
```

### Debug Mode

Enable detailed logging:
```bash
docker exec goodreads-sync sh -c "LOG_LEVEL=DEBUG HEADLESS=false python -m sync.main"
```

### Viewing Error Screenshots

When errors occur, screenshots are saved automatically:
```bash
ls -ltr data/artifacts/screenshots/
```

Open them to see what the browser saw when the error occurred.

---

## Advanced Configuration

### Custom Browser Timeout

For slow internet connections:
```bash
# In .env
BROWSER_TIMEOUT=60000  # 60 seconds (default is 30)
```

### Storage State Expiry

Control how long sessions are reused:
```bash
# In .env
STORAGE_STATE_EXPIRY_DAYS=14  # Re-login after 14 days (default is 30)
```

### Limited Testing

Sync only first N books (for testing):
```bash
docker exec goodreads-sync sh -c "MAX_SYNC_ITEMS=50 python -m sync.main"
```

### Custom Data Directory

Mount a different local directory:
```yaml
# In docker-compose.yml
volumes:
  - /path/to/custom/data:/data
```

### Running Without Docker

If you prefer to run locally:
```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium --with-deps

# Run sync
python -m sync.main
```

Note: You'll need to manually set up cron or Task Scheduler for automation.

---

## Known Limitations

### 1. CAPTCHA Risk
If either site adds CAPTCHA, automation will break. Mitigation: Run less frequently, maintain valid sessions.

### 2. UI Changes
Website UI changes may break selectors. Solution: Update `sync/selectors.py` when this occurs.

### 3. Rate Limiting
Running too frequently may trigger rate limits or account flags. Recommendation: Once daily is safe.

### 4. Terms of Service
Automation may violate site ToS. Use at your own risk. This tool is for personal use only.

### 5. No 2FA Support
Accounts must have two-factor authentication disabled. This is a security trade-off.

### 6. Session Expiry
Storage state may expire randomly. Service will auto-retry with fresh login.

### 7. Network Dependency
Requires stable internet connection. Transient failures will be logged but may cause sync to fail.

### 8. No Incremental Sync
Always uploads full library. StoryGraph handles deduplication server-side.

---

## FAQ

### Q: Will this create duplicate books in StoryGraph?
**A:** No. StoryGraph's import process handles deduplication automatically. Existing books are matched and updated, not duplicated.

### Q: How often should I run the sync?
**A:** Once daily is recommended (default: 3 AM). More frequent syncing increases CAPTCHA and rate limit risks.

### Q: Can I sync multiple Goodreads accounts?
**A:** Not with a single container. You'd need to run separate containers with different `.env` files.

### Q: What happens if my Goodreads library hasn't changed?
**A:** The sync intelligently skips the upload step, saving time and reducing server load.

### Q: How do I force a re-sync?
**A:** Set `FORCE_FULL_SYNC=true` in `.env` or run:
```bash
docker exec goodreads-sync sh -c "FORCE_FULL_SYNC=true python -m sync.main"
```

### Q: Where are my credentials stored?
**A:** In the `.env` file (never committed to git). Inside the container, they're in environment variables.

### Q: Is this secure?
**A:** Credentials are stored in plain text in `.env`. Ensure file permissions are restrictive (`chmod 600 .env`). Docker volume is local-only.

### Q: Can I run this on a Raspberry Pi?
**A:** Yes, but performance may be slow. Chromium + Playwright requires ~1GB RAM. Use a Pi 4 with at least 2GB RAM.

### Q: What if I change my password?
**A:** Update `.env` and delete storage state files:
```bash
rm data/state/playwright_storage_*.json
docker compose restart
```

### Q: How do I update the sync service?
**A:** Pull latest code and rebuild:
```bash
git pull
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Q: Can I see the browser while it runs?
**A:** Yes, set `HEADLESS=false` and run manually:
```bash
docker exec goodreads-sync sh -c "HEADLESS=false python -m sync.main"
```
Note: This requires X11 forwarding or VNC if running remotely.

---

## Support & Contributions

- **Issues**: Report bugs or request features via GitHub Issues
- **Pull Requests**: Contributions welcome! Please test thoroughly before submitting
- **Selectors**: If UI changes break sync, PRs updating `sync/selectors.py` are especially valuable

---

**Last Updated**: 2026-01-15
**Version**: 1.0.0
