"""Centralized path management for local and Docker environments."""

from pathlib import Path


def data_root() -> Path:
    """Get the data root directory.

    Prefers local ./data (for development) over /data (Docker).
    Creates the directory if it doesn't exist.
    """
    local = Path("data")
    if local.exists() or not Path("/data").exists():
        return local
    return Path("/data")


def state_dir() -> Path:
    """Get the state directory."""
    d = data_root() / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifacts_dir() -> Path:
    """Get the artifacts directory."""
    d = data_root() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    """Get the logs directory."""
    d = data_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    """Get the config directory."""
    return data_root() / "config"
