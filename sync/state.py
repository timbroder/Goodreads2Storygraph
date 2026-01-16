"""State management for tracking sync history and CSV hashes."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .exceptions import StateError


def get_state_file(account_name: str) -> Path:
    """
    Get state file path for a specific account.

    Args:
        account_name: Unique account identifier

    Returns:
        Path to account's state file
    """
    return Path(f"/data/state/last_sync_state_{account_name}.json")


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


def load_state(account_name: str) -> Optional[dict]:
    """
    Load the last sync state from disk for a specific account.

    Args:
        account_name: Unique account identifier

    Returns:
        State dictionary with keys: last_hash, last_sync_timestamp, last_book_count
        Returns None if state file doesn't exist or is invalid
    """
    state_file = get_state_file(account_name)
    if not state_file.exists():
        return None

    try:
        with open(state_file, "r") as f:
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


def save_state(csv_hash: str, book_count: int, account_name: str) -> None:
    """
    Save sync state to disk for a specific account.

    Args:
        csv_hash: SHA256 hash of the synced CSV
        book_count: Number of books in the CSV
        account_name: Unique account identifier
    """
    state_file = get_state_file(account_name)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "last_hash": csv_hash,
        "last_sync_timestamp": datetime.utcnow().isoformat(),
        "last_book_count": book_count,
        "account_name": account_name
    }

    try:
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        raise StateError(f"Failed to save state: {e}")


def should_skip_upload(csv_path: str, account_name: str, force_sync: bool = False) -> tuple[bool, str]:
    """
    Determine if upload should be skipped based on CSV hash comparison for a specific account.

    Args:
        csv_path: Path to the current CSV file
        account_name: Unique account identifier
        force_sync: If True, never skip upload

    Returns:
        Tuple of (should_skip, reason)
    """
    if force_sync:
        return False, "Force sync enabled"

    current_hash = calculate_csv_hash(csv_path)
    state = load_state(account_name)

    if state is None:
        return False, "No previous state found"

    if state["last_hash"] == current_hash:
        return True, f"CSV unchanged since {state['last_sync_timestamp']}"

    return False, "CSV has changed"
