# /data Directory Structure

This directory contains all persistent data for the Goodreads → StoryGraph sync service. It is mounted as a volume in the Docker container and excluded from git tracking.

## Directory Layout

```
data/
├── logs/                           # Log files
│   ├── sync.log                   # Main rotating log file
│   └── runs/                      # Per-run log files
│       └── YYYYMMDD_HHMMSS.log   # Individual sync run logs
│
├── artifacts/                      # Generated files and debug data
│   ├── goodreads_export_*.csv     # Exported Goodreads CSV files
│   ├── screenshots/               # Error screenshots
│   │   └── YYYYMMDD_HHMMSS/      # Timestamped screenshot folders
│   └── html/                      # Error page HTML snapshots
│       └── YYYYMMDD_HHMMSS/      # Timestamped HTML folders
│
└── state/                          # Persistent state files
    ├── playwright_storage_goodreads.json    # Goodreads session cookies
    ├── playwright_storage_storygraph.json   # StoryGraph session cookies
    └── last_sync_state.json                 # Last sync metadata
```

## File Descriptions

### Logs

- **sync.log**: Main log file with all sync operations. Includes timestamps, info, warnings, and errors.
- **runs/*.log**: Individual log files for each sync run, named with timestamp.

### Artifacts

- **goodreads_export_*.csv**: CSV files exported from Goodreads. Timestamped to preserve history.
- **screenshots/**: PNG screenshots captured during errors for debugging.
- **html/**: HTML page snapshots captured during errors for debugging.

### State

- **playwright_storage_*.json**: Browser session storage including cookies and localStorage. Allows reusing login sessions without re-authenticating.
- **last_sync_state.json**: Metadata from the last successful sync:
  ```json
  {
    "last_hash": "sha256_hash_of_csv",
    "last_sync_timestamp": "2026-01-15T12:00:00Z",
    "last_book_count": 123
  }
  ```

## Automatic Creation

These directories are automatically created by:
1. The Docker entrypoint script (`docker/entrypoint.sh`) on container startup
2. The sync application as needed during operation

## Cleanup

- **Run logs**: Automatically deleted after 30 days by `sync_wrapper.sh`
- **CSVs**: Kept indefinitely (manually delete old ones if needed)
- **Screenshots**: Kept indefinitely (manually clean up as needed)
- **Session files**: Automatically updated/refreshed as needed

## Troubleshooting

### Logs Not Appearing

- Check volume mount: `docker inspect goodreads2storygraph-sync | grep Mounts`
- Verify permissions: Container runs as user `syncuser` (UID 1000)
- Check for errors: `docker logs goodreads2storygraph-sync`

### State Not Persisting

- Ensure `/data` is properly mounted in `docker-compose.yml`
- Verify `last_sync_state.json` is valid JSON
- Check file permissions

### Session Expired

- Delete `playwright_storage_*.json` files to force re-login
- Container will automatically recreate them on next run

## Data Volume Management

### Backup

```bash
# Backup entire data directory
tar -czf goodreads-sync-backup-$(date +%Y%m%d).tar.gz data/
```

### Restore

```bash
# Restore from backup
tar -xzf goodreads-sync-backup-YYYYMMDD.tar.gz
```

### Reset

```bash
# Clear all data and start fresh
rm -rf data/*
docker compose restart
```

## Security Notes

- **State files contain session cookies** - keep this directory secure
- **Logs may contain email addresses** - be careful when sharing logs
- **CSVs contain your library data** - personal information
- Set appropriate file permissions: `chmod 700 data/`
