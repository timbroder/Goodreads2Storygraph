# 📚 Goodreads → StoryGraph Sync

> Automated Docker service for syncing your Goodreads library to TheStoryGraph

[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/playwright-automated-orange.svg)](https://playwright.dev/)

---

## 🎯 What Is This?

A fully automated service that keeps your Goodreads and StoryGraph libraries in sync. Set it up once, and it runs on a schedule (default: daily at 3 AM), intelligently syncing your reading data without manual intervention.

### Why?

Manually exporting from Goodreads and importing to StoryGraph is tedious. This tool automates the entire process:
- Exports your Goodreads library
- Uploads it to StoryGraph
- Skips uploads when nothing has changed
- Runs on your schedule
- Logs everything for troubleshooting

---

## ✨ Features

- ✅ **Fully Automated** - Set-it-and-forget-it scheduling with cron
- ✅ **Smart Sync** - Only uploads when your library changes (hash-based comparison)
- ✅ **Session Persistence** - Reuses login sessions to avoid repeated logins
- ✅ **Docker-Based** - No manual dependency management
- ✅ **Comprehensive Logging** - Per-run logs with timestamps and error screenshots
- ✅ **Dry Run Mode** - Test without affecting your StoryGraph library
- ✅ **Zero Duplicates** - StoryGraph handles deduplication automatically

---

## 🚀 Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- Goodreads account (with books)
- StoryGraph account
- **Important**: Disable 2FA on both accounts (automation requirement)

### 2. Setup

```bash
# Clone the repository
git clone <repository-url>
cd Goodreads2Storygraph

# Create environment file
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Minimum required configuration in `.env`:**
```bash
GOODREADS_EMAIL=your-email@example.com
GOODREADS_PASSWORD=your-password
STORYGRAPH_EMAIL=your-email@example.com
STORYGRAPH_PASSWORD=your-password
```

### 3. Start the Service

```bash
# Create data directory
mkdir -p data/{logs/runs,artifacts,state}

# Build and start
docker compose up -d
```

That's it! The service will now run automatically based on your schedule (default: daily at 3 AM).

---

## 📖 Usage

### Manual Sync

Run a sync immediately:
```bash
docker exec goodreads-sync python -m sync.main
```

### View Logs

```bash
# Real-time container logs
docker logs -f goodreads-sync

# Main sync log
tail -f data/logs/sync.log

# Per-run logs
ls data/logs/runs/
```

### Test Without Uploading

```bash
docker exec goodreads-sync sh -c "DRY_RUN=true python -m sync.main"
```

### Force Full Sync

```bash
docker exec goodreads-sync sh -c "FORCE_FULL_SYNC=true python -m sync.main"
```

---

## ⚙️ Configuration

### Scheduling

Edit `CRON_SCHEDULE` in `.env`:

```bash
# Daily at 3 AM (default)
CRON_SCHEDULE=0 3 * * *

# Every 6 hours
CRON_SCHEDULE=0 */6 * * *

# Twice daily (6 AM and 6 PM)
CRON_SCHEDULE=0 6,18 * * *
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SCHEDULE` | `0 3 * * *` | When to run sync |
| `TZ` | `America/New_York` | Timezone |
| `HEADLESS` | `true` | Hide browser window |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `DRY_RUN` | `false` | Test mode (no upload) |
| `FORCE_FULL_SYNC` | `false` | Ignore change detection |

See [`.env.example`](.env.example) for all options.

---

## 🔍 How It Works

1. **Export**: Logs into Goodreads and downloads your library CSV
2. **Compare**: Calculates hash and checks if library changed since last sync
3. **Upload**: If changed (or forced), uploads CSV to StoryGraph
4. **Track**: Saves state to avoid redundant uploads
5. **Repeat**: Runs on schedule automatically

### Smart Skip Logic

The service maintains a hash of your last exported CSV. If your Goodreads library hasn't changed, it skips the upload step entirely. This:
- Saves time
- Reduces server load
- Minimizes CAPTCHA risk
- Respects rate limits

---

## 📁 Project Structure

```
Goodreads2Storygraph/
├── sync/                      # Core Python package
│   ├── main.py               # Entry point & orchestration
│   ├── goodreads.py          # Goodreads export automation
│   ├── storygraph.py         # StoryGraph upload automation
│   ├── state.py              # Hash tracking & persistence
│   ├── transform.py          # CSV validation
│   ├── selectors.py          # Web element selectors
│   ├── logging_setup.py      # Logging configuration
│   └── exceptions.py         # Custom exceptions
├── docker/                    # Docker infrastructure
│   ├── Dockerfile            # Container image
│   ├── entrypoint.sh         # Startup script
│   └── crontab               # Cron template
├── data/                      # Persistent data (mounted volume)
│   ├── logs/                 # Sync logs
│   ├── artifacts/            # Exported CSVs & screenshots
│   └── state/                # Session & sync state
├── docker-compose.yml        # Service orchestration
├── .env.example              # Configuration template
└── README_SYNC.md            # Detailed documentation
```

---

## 🛠️ Troubleshooting

### Login Issues

Delete session files and retry:
```bash
rm data/state/playwright_storage_*.json
docker compose restart
```

### Check Container Status

```bash
# Is it running?
docker ps | grep goodreads-sync

# Is cron configured?
docker exec goodreads-sync crontab -l

# Recent logs
docker logs --tail 50 goodreads-sync
```

### Debug Mode

Run with full logging:
```bash
docker exec goodreads-sync sh -c "LOG_LEVEL=DEBUG python -m sync.main"
```

### Error Screenshots

When errors occur, screenshots are automatically saved:
```bash
ls data/artifacts/screenshots/
```

For more troubleshooting, see [README_SYNC.md](README_SYNC.md#troubleshooting).

---

## ⚠️ Known Limitations

1. **No 2FA Support** - Both accounts must have two-factor authentication disabled
2. **CAPTCHA Risk** - Frequent automation may trigger CAPTCHA challenges
3. **UI Changes** - Website updates may break selectors (requires updates to `sync/selectors.py`)
4. **Terms of Service** - Automation may violate site ToS (use at your own risk)
5. **Full Sync Only** - Uploads entire library each time (StoryGraph deduplicates)
6. **Network Dependency** - Requires stable internet connection

---

## 🔒 Security Notes

- Credentials are stored in `.env` (excluded from git via `.gitignore`)
- Ensure proper file permissions: `chmod 600 .env`
- Browser sessions cached in `/data/state/` (local volume only)
- No data transmitted to third parties
- All automation happens in your local Docker container

---

## 📚 Documentation

- **[README_SYNC.md](README_SYNC.md)** - Detailed setup, configuration, and troubleshooting
- **[.env.example](.env.example)** - All available configuration options
- **[PROJECT_PLAN.md](PROJECT_PLAN.md)** - Implementation details and architecture

---

## 🤝 Contributing

Contributions welcome! Especially valuable:
- Updates to `sync/selectors.py` when websites change
- Bug fixes and error handling improvements
- Documentation enhancements
- Testing on different platforms

Please test thoroughly and include:
1. Description of changes
2. Testing performed
3. Any breaking changes

---

## ❓ FAQ

**Q: Will this create duplicates in StoryGraph?**
A: No. StoryGraph's import system handles deduplication automatically.

**Q: How often should I sync?**
A: Once daily (default) is recommended. More frequent syncing increases CAPTCHA risk.

**Q: Can I run this without Docker?**
A: Yes, but you'll need to manually install Python, Playwright, and set up scheduling. See [README_SYNC.md](README_SYNC.md#running-without-docker).

**Q: What happens if my library hasn't changed?**
A: The sync detects this via hash comparison and skips the upload, saving time.

**Q: Is this safe?**
A: The tool runs locally in Docker. Your credentials never leave your machine. However, automation may violate site ToS.

For more questions, see [README_SYNC.md](README_SYNC.md#faq).

---

## 📜 License

This project is provided as-is for personal use. Use at your own risk. The authors are not responsible for any violations of terms of service or account issues.

---

## 🙏 Acknowledgments

- Built with [Playwright](https://playwright.dev/) for browser automation
- Inspired by the need for better cross-platform reading tracking
- Thanks to Goodreads and StoryGraph for great reading platforms

---

**Happy Reading!** 📖✨

For detailed documentation, see [README_SYNC.md](README_SYNC.md).
