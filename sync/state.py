"""State management for tracking sync history and CSV hashes."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .exceptions import StateError


STATE_FILE = Path("/data/state/last_sync_state.json")


def calculate_csv_hash(filepath: str) -> str:
    """
    Calculate SHA256 hash of a CSV file.

    Args:
        filepath: Path to the CSV file

    Returns:
        Hex digest of the file hash
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        raise StateError(f"Failed to calculate hash for {filepath}: {e}")


def load_state() -> Optional[dict]:
    """
    Load the last sync state from disk.

    Returns:
        State dictionary with keys: last_hash, last_sync_timestamp, last_book_count
        Returns None if state file doesn't exist or is invalid
    """
    if not STATE_FILE.exists():
        return None

    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)

        # Validate state structure
        required_keys = {"last_hash", "last_sync_timestamp", "last_book_count"}
        if not all(key in state for key in required_keys):
            raise StateError("State file missing required keys")

        return state
    except json.JSONDecodeError as e:
        raise StateError(f"State file is corrupted: {e}")
    except Exception as e:
        raise StateError(f"Failed to load state: {e}")


def save_state(csv_hash: str, book_count: int) -> None:
    """
    Save sync state to disk.

    Args:
        csv_hash: SHA256 hash of the synced CSV
        book_count: Number of books in the CSV
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "last_hash": csv_hash,
        "last_sync_timestamp": datetime.utcnow().isoformat(),
        "last_book_count": book_count
    }

    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        raise StateError(f"Failed to save state: {e}")


def should_skip_upload(csv_path: str, force_sync: bool = False) -> tuple[bool, str]:
    """
    Determine if upload should be skipped based on CSV hash comparison.

    Args:
        csv_path: Path to the current CSV file
        force_sync: If True, never skip upload

    Returns:
        Tuple of (should_skip, reason)
    """
    if force_sync:
        return False, "Force sync enabled"

    current_hash = calculate_csv_hash(csv_path)
    state = load_state()

    if state is None:
        return False, "No previous state found"

    if state["last_hash"] == current_hash:
        return True, f"CSV unchanged since {state['last_sync_timestamp']}"

    return False, "CSV has changed"
