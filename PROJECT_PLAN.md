# Goodreads → TheStoryGraph Docker Sync Service - Implementation Plan

## 📋 Project Architecture Overview

### Core Design Decisions (Based on Requirements)
1. **No CSV transformation** - Upload raw Goodreads CSV directly to StoryGraph
2. **Full sync every time** - Let StoryGraph handle deduplication
3. **Smart skip logic** - Compare CSV hash; skip upload if unchanged
4. **Instant operations** - Both export and import are synchronous (no polling needed)
5. **Chromium-only** - Keeps image ~1GB, runtime ~500MB-1GB RAM

---

## 🏗️ Module Breakdown

### `/sync/` - Core Python Package

**`exceptions.py`**
- `GoodreadsExportError` - Failed to export/download
- `StoryGraphUploadError` - Failed to upload/verify
- `StateError` - State file corruption
- `PlaywrightError` - Browser automation failures

**`selectors.py`**
- Centralized CSS/XPath selectors for both sites
- Organized by site and action (login, export, upload)
- Easy to update when UI changes

**`logging_setup.py`**
- Dual logging: console + rotating file
- Per-run log files: `/data/logs/runs/<timestamp>.log`
- Main log: `/data/logs/sync.log`
- Structured format with timestamps

**`state.py`**
- `load_state()` - Read `last_sync_state.json`
- `save_state(csv_hash, timestamp, book_count)` - Persist after success
- `calculate_csv_hash(filepath)` - SHA256 hash for comparison
- State schema: `{last_hash, last_sync_timestamp, last_book_count}`

**`transform.py`**
- `validate_csv(filepath)` - Check CSV integrity
- `calculate_hash(filepath)` - Wrapper for state.py function
- `count_books(filepath)` - Parse and count rows
- Minimal logic since no transformation needed

**`goodreads.py`**
- `GoodreadsClient(playwright, config)`
- `login()` - Uses storage state if valid, else logs in
- `export_library()` - Navigate to export, trigger download
- `_save_storage_state()` - Persist session
- Robust error handling with screenshots

**`storygraph.py`**
- `StoryGraphClient(playwright, config)`
- `login()` - Uses storage state if valid, else logs in
- `upload_csv(filepath)` - Navigate to import, upload file, verify success
- `_save_storage_state()` - Persist session
- Waits for success indicator

**`main.py`**
- CLI entry point: `python -m sync.main`
- Orchestrates full sync workflow:
  1. Initialize Playwright + browser
  2. Export from Goodreads → `/data/artifacts/goodreads_export_<timestamp>.csv`
  3. Calculate hash and compare with last state
  4. If unchanged and not `FORCE_FULL_SYNC`, skip upload
  5. Else upload to StoryGraph
  6. Update state on success
- Respects `DRY_RUN`, `MAX_SYNC_ITEMS`, etc.
- Comprehensive error handling and cleanup

---

## 🐳 Docker Infrastructure

### `docker/Dockerfile`
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
# - Install Python 3.11+
# - Install cron
# - Copy requirements.txt and install deps
# - playwright install chromium --with-deps
# - Create /data volume structure
# - Non-root user (with cron compatibility)
# - WORKDIR /app
```

### `docker/entrypoint.sh`
```bash
# - Inject CRON_SCHEDULE into crontab
# - Set timezone from TZ env var
# - Validate /data mounts
# - Start cron in foreground (cron -f)
```

### `docker/crontab`
```
# Template with placeholder: {{CRON_SCHEDULE}} /app/sync_wrapper.sh
# Wrapper script handles: python -m sync.main >> /data/logs/sync.log 2>&1
```

### `docker-compose.yml`
```yaml
services:
  goodreads-sync:
    build: ./docker
    volumes:
      - ./data:/data
      - ./sync:/app/sync
    env_file: .env
    restart: unless-stopped
    environment:
      - TZ=${TZ:-America/New_York}
```

---

## 📁 Volume Layout (`/data/`)

```
/data/
├── logs/
│   ├── sync.log                          # Main log (rotating)
│   └── runs/
│       └── 2026-01-14_030000.log         # Per-run logs
├── artifacts/
│   ├── goodreads_export_20260114_030000.csv
│   ├── screenshots/
│   │   └── 20260114_030000/
│   │       ├── goodreads_login_failed.png
│   │       └── storygraph_upload_step.png
│   └── html/
│       └── 20260114_030000/
│           └── error_page.html
└── state/
    ├── playwright_storage_goodreads.json  # Session cookies
    ├── playwright_storage_storygraph.json # Session cookies
    └── last_sync_state.json               # Hash + metadata
```

---

## 🔒 Environment Variables

**Required:**
- `GOODREADS_EMAIL`
- `GOODREADS_PASSWORD`
- `STORYGRAPH_EMAIL`
- `STORYGRAPH_PASSWORD`

**Optional:**
- `CRON_SCHEDULE` (default: `0 3 * * *`)
- `TZ` (default: `America/New_York`)
- `HEADLESS` (default: `true`)
- `LOG_LEVEL` (default: `INFO`)
- `MAX_SYNC_ITEMS` (default: no limit)
- `DRY_RUN` (default: `false`)
- `FORCE_FULL_SYNC` (default: `false`)

---

## 🧪 Testing Strategy

### Unit Tests (`pytest`)
- `test_transform.py` - CSV validation, hash calculation
- `test_state.py` - State load/save, hash comparison

### Manual Testing Checklist
1. ✅ `python -m sync.main` - Single run succeeds
2. ✅ `DRY_RUN=true` - Exports but doesn't upload
3. ✅ Second run with unchanged library - Skips upload
4. ✅ `FORCE_FULL_SYNC=true` - Uploads even if unchanged
5. ✅ Container starts: `docker compose up -d`
6. ✅ Cron executes at scheduled time
7. ✅ Logs and artifacts appear in `./data/`
8. ✅ Failure scenarios capture screenshots + HTML

---

## 🎯 Success Criteria

✅ **Manual execution works**: `docker exec <container> python -m sync.main`
✅ **Cron runs automatically**: Check `/data/logs/runs/` for new logs
✅ **Idempotent**: Repeated runs with unchanged library skip upload
✅ **Error resilience**: Screenshots + HTML + logs on failures
✅ **Session persistence**: Reuses browser sessions from `/data/state/`
✅ **No duplicates**: StoryGraph handles dedup correctly

---

## ⚠️ Known Limitations (for README)

1. **CAPTCHA risk** - If either site adds CAPTCHA, automation breaks
2. **UI changes** - Selectors in `selectors.py` may need updates
3. **Rate limiting** - Running too frequently might trigger blocks
4. **ToS compliance** - Automation may violate terms of service
5. **No 2FA support** - Accounts must have 2FA disabled
6. **Session expiry** - Storage state may expire; will re-login

---

## 📦 Implementation Tasks

### Phase 1: Core Python Package (11 files) ✅
- [x] Create project directory structure (/sync, /docker, /tests)
- [x] Create requirements.txt with Playwright, pytest, and dependencies
- [x] Implement sync/__init__.py (package initialization)
- [x] Implement sync/exceptions.py (custom exception classes)
- [x] Implement sync/selectors.py (CSS/XPath selectors for both sites)
- [x] Implement sync/logging_setup.py (dual file/console logging)
- [x] Implement sync/state.py (CSV hash tracking, state persistence)
- [x] Implement sync/goodreads.py (login, export, download with Playwright)
- [x] Implement sync/storygraph.py (login, upload, verify with Playwright)
- [x] Implement sync/transform.py (CSV hash calculation, file validation)
- [x] Implement sync/main.py (orchestration, CLI entry point, DRY_RUN support)

### Phase 2: Docker Infrastructure (4 files) ✅
- [x] Create docker/Dockerfile (Playwright Python base, cron setup)
- [x] Create docker/entrypoint.sh (inject CRON_SCHEDULE, start cron)
- [x] Create docker/crontab template
- [x] Create docker-compose.yml (volume mounts, env vars, restart policy)

### Phase 3: Configuration & Documentation (4 files) ✅
- [x] Create .env.example (template for all required env vars)
- [x] Create .gitignore (exclude .env, /data, __pycache__, etc.)
- [x] Create README_SYNC.md (setup, usage, troubleshooting, limitations)
- [x] Create main README.md (project overview, quick start)

### Phase 4: Testing (4 tasks) ✅
- [x] Implement tests/test_transform.py (CSV hash, validation)
- [x] Implement tests/test_state.py (state persistence logic)
- [x] Test manual execution: python -m sync.main
- [x] Build Docker image and test container startup

### Phase 5: Integration & Deployment (3 tasks) ✅
- [x] Test cron scheduling inside container
- [x] Verify artifacts and logs in /data volume
- [x] Commit all changes and push to branch

---

## 📊 Progress Tracking

**Total Tasks**: 26
**Completed**: 26
**In Progress**: 0
**Remaining**: 0

**Current Phase**: Phase 5 Complete ✅ - All Phases Complete!

---

## 🔄 Session Recovery Notes

If a session is interrupted, resume by:
1. Check this file for progress
2. Review the TodoWrite list status
3. Continue from the last incomplete task
4. Update checkboxes as tasks complete

---

**Last Updated**: 2026-01-15
**Branch**: `claude/phase-5-C8xOj`
**Status**: Phase 5 Complete - All Implementation Complete ✅
