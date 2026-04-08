"""State management for tracking sync history and per-book sync status."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from .exceptions import StateError
from .models import BookRecord, DeltaResult


def _data_dir() -> Path:
    """Get the data directory, preferring local ./data over /data."""
    local = Path("data/state")
    if local.exists() or not Path("/data").exists():
        return local
    return Path("/data/state")


def get_state_file(account_name: str) -> Path:
    """Get state file path for a specific account."""
    return _data_dir() / f"last_sync_state_{account_name}.json"


def calculate_csv_hash(filepath: str) -> str:
    """Calculate SHA256 hash of a CSV file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        raise StateError(f"Failed to calculate hash for {filepath}: {e}")


def _migrate_v1_to_v2(state: dict) -> dict:
    """Migrate a v1 state dict to v2 schema."""
    return {
        "schema_version": 2,
        "last_csv_hash": state.get("last_hash", ""),
        "last_sync_timestamp": state.get("last_sync_timestamp", ""),
        "last_book_count": state.get("last_book_count", 0),
        "account_name": state.get("account_name", ""),
        "books": {},
        "failed_books": {},
    }


def load_state(account_name: str) -> Optional[dict]:
    """
    Load the sync state from disk, auto-migrating v1 to v2.

    Returns None if state file doesn't exist.
    """
    state_file = get_state_file(account_name)
    if not state_file.exists():
        return None

    try:
        with open(state_file, "r") as f:
            state = json.load(f)

        # Migrate v1 -> v2 if needed
        if state.get("schema_version") != 2:
            state = _migrate_v1_to_v2(state)

        return state
    except json.JSONDecodeError as e:
        raise StateError(f"State file is corrupted: {e}")
    except Exception as e:
        raise StateError(f"Failed to load state: {e}")


def save_state(csv_hash: str, book_count: int, account_name: str,
               books: Optional[dict] = None, failed_books: Optional[dict] = None) -> None:
    """
    Save sync state to disk in v2 format.

    Args:
        csv_hash: SHA256 hash of the synced CSV
        book_count: Number of books in the CSV
        account_name: Unique account identifier
        books: Per-book sync status dict (optional, preserved from existing state if not provided)
        failed_books: Per-book failure tracking dict (optional)
    """
    state_file = get_state_file(account_name)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing state to preserve book-level data if not provided
    existing = None
    if books is None or failed_books is None:
        try:
            existing = load_state(account_name)
        except StateError:
            existing = None

    state = {
        "schema_version": 2,
        "last_csv_hash": csv_hash,
        "last_sync_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_book_count": book_count,
        "account_name": account_name,
        "books": books if books is not None else (existing or {}).get("books", {}),
        "failed_books": failed_books if failed_books is not None else (existing or {}).get("failed_books", {}),
    }

    try:
        # Write atomically via temp file
        tmp_path = state_file.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2)
        tmp_path.replace(state_file)
    except Exception as e:
        raise StateError(f"Failed to save state: {e}")


def mark_book_synced(account_name: str, book_id: str, row_hash: str) -> None:
    """Record a successful book sync in the state file."""
    state = load_state(account_name)
    if state is None:
        state = {
            "schema_version": 2,
            "last_csv_hash": "",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": account_name,
            "books": {},
            "failed_books": {},
        }

    state["books"][book_id] = {
        "row_hash": row_hash,
        "last_synced": datetime.now(timezone.utc).isoformat(),
        "status": "synced",
    }

    # Remove from failed if it was there
    state.get("failed_books", {}).pop(book_id, None)

    save_state(
        csv_hash=state["last_csv_hash"],
        book_count=state["last_book_count"],
        account_name=account_name,
        books=state["books"],
        failed_books=state.get("failed_books", {}),
    )


def mark_book_failed(account_name: str, book_id: str, row_hash: str, error: str) -> None:
    """Record a failed book sync in the state file."""
    state = load_state(account_name)
    if state is None:
        state = {
            "schema_version": 2,
            "last_csv_hash": "",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": account_name,
            "books": {},
            "failed_books": {},
        }

    existing_failure = state.get("failed_books", {}).get(book_id, {})
    retry_count = existing_failure.get("retry_count", 0) + 1

    state.setdefault("failed_books", {})[book_id] = {
        "row_hash": row_hash,
        "last_attempt": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "retry_count": retry_count,
    }

    save_state(
        csv_hash=state["last_csv_hash"],
        book_count=state["last_book_count"],
        account_name=account_name,
        books=state.get("books", {}),
        failed_books=state["failed_books"],
    )


def compute_delta(
    csv_books: Dict[str, BookRecord],
    state: Optional[dict],
    max_retries: int = 3,
) -> DeltaResult:
    """
    Compare current CSV books against stored state to find what needs syncing.

    Args:
        csv_books: Dict of book_id -> BookRecord from current CSV
        state: Loaded state dict (may be None for first run)
        max_retries: Maximum retry attempts for failed books

    Returns:
        DeltaResult with new, changed, removed, and retryable books
    """
    if state is None:
        return DeltaResult(
            new_books=list(csv_books.values()),
            changed_books=[],
            removed_book_ids=[],
            unchanged_count=0,
            retryable_books=[],
        )

    synced_books = state.get("books", {})
    failed_books = state.get("failed_books", {})

    new = []
    changed = []
    unchanged_count = 0
    retryable = []

    for book_id, book in csv_books.items():
        if book_id in synced_books:
            if book.row_hash() != synced_books[book_id].get("row_hash"):
                changed.append(book)
            else:
                unchanged_count += 1
        elif book_id in failed_books:
            if failed_books[book_id].get("retry_count", 0) < max_retries:
                retryable.append(book)
            # else: exceeded max retries, skip
        else:
            new.append(book)

    # Detect removed books (in state but not in CSV)
    all_csv_ids = set(csv_books.keys())
    all_synced_ids = set(synced_books.keys())
    removed = list(all_synced_ids - all_csv_ids)

    return DeltaResult(
        new_books=new,
        changed_books=changed,
        removed_book_ids=removed,
        unchanged_count=unchanged_count,
        retryable_books=retryable,
    )


def should_skip_upload(csv_path: str, account_name: str, force_sync: bool = False) -> tuple[bool, str]:
    """
    Determine if sync should be skipped based on CSV hash comparison.

    This is a fast-path check before parsing individual books.
    """
    if force_sync:
        return False, "Force sync enabled"

    current_hash = calculate_csv_hash(csv_path)
    state = load_state(account_name)

    if state is None:
        return False, "No previous state found"

    last_hash = state.get("last_csv_hash") or state.get("last_hash", "")
    if last_hash == current_hash:
        return True, f"CSV unchanged since {state.get('last_sync_timestamp', 'unknown')}"

    return False, "CSV has changed"
