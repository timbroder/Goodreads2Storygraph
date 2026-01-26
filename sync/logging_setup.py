"""Logging configuration for dual console and rotating file logging."""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import get_data_path


def setup_logging(log_level: str = "INFO") -> tuple[logging.Logger, str]:
    """
    Setup dual logging: console + rotating file + per-run log file.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Tuple of (logger, run_log_path)
    """
    # Create log directories
    log_dir = get_data_path() / "logs"
    runs_dir = log_dir / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger("sync")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Main rotating file handler
    main_log_path = log_dir / "sync.log"
    file_handler = RotatingFileHandler(
        main_log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Per-run log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_path = runs_dir / f"{timestamp}.log"
    run_handler = logging.FileHandler(run_log_path)
    run_handler.setLevel(logging.DEBUG)  # Capture everything in run logs
    run_handler.setFormatter(formatter)
    logger.addHandler(run_handler)

    logger.info(f"Logging initialized. Run log: {run_log_path}")

    return logger, str(run_log_path)
