"""Configuration management for single and multi-account setups."""

import json
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from .exceptions import SyncError


class AccountConfig:
    """Configuration for a single account pair."""

    def __init__(
        self,
        name: str,
        goodreads_email: str,
        goodreads_password: str,
        storygraph_email: str,
        storygraph_password: str,
    ):
        """
        Initialize account configuration.

        Args:
            name: Unique account identifier (alphanumeric and underscores only)
            goodreads_email: Goodreads login email
            goodreads_password: Goodreads login password
            storygraph_email: StoryGraph login email
            storygraph_password: StoryGraph login password
        """
        self.name = name
        self.goodreads_email = goodreads_email
        self.goodreads_password = goodreads_password
        self.storygraph_email = storygraph_email
        self.storygraph_password = storygraph_password

    def validate(self) -> None:
        """
        Validate account configuration.

        Raises:
            SyncError: If validation fails
        """
        if not self.name or not self.name.replace("_", "").isalnum():
            raise SyncError(
                f"Account name '{self.name}' must contain only alphanumeric characters and underscores"
            )

        required_fields = {
            "goodreads_email": self.goodreads_email,
            "goodreads_password": self.goodreads_password,
            "storygraph_email": self.storygraph_email,
            "storygraph_password": self.storygraph_password,
        }

        missing = [field for field, value in required_fields.items() if not value]
        if missing:
            raise SyncError(
                f"Account '{self.name}' missing required fields: {', '.join(missing)}"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "AccountConfig":
        """
        Create AccountConfig from dictionary.

        Args:
            data: Dictionary with account configuration

        Returns:
            AccountConfig instance

        Raises:
            SyncError: If required fields are missing
        """
        try:
            return cls(
                name=data["name"],
                goodreads_email=data["goodreads_email"],
                goodreads_password=data["goodreads_password"],
                storygraph_email=data["storygraph_email"],
                storygraph_password=data["storygraph_password"],
            )
        except KeyError as e:
            raise SyncError(f"Account configuration missing required field: {e}")


class Config:
    """Global configuration including accounts and sync settings."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        headless: bool = True,
        log_level: str = "INFO",
        dry_run: bool = False,
        force_sync: bool = False,
        max_sync_items: Optional[int] = None,
    ):
        """
        Initialize configuration.

        Args:
            accounts: List of account configurations
            headless: Run browser in headless mode
            log_level: Logging level
            dry_run: Export but don't upload
            force_sync: Force upload even if unchanged
            max_sync_items: Maximum items to sync (for testing)
        """
        self.accounts = accounts
        self.headless = headless
        self.log_level = log_level
        self.dry_run = dry_run
        self.force_sync = force_sync
        self.max_sync_items = max_sync_items

    def validate(self) -> None:
        """
        Validate configuration.

        Raises:
            SyncError: If validation fails
        """
        if not self.accounts:
            raise SyncError("No accounts configured")

        # Check for duplicate account names
        names = [acc.name for acc in self.accounts]
        duplicates = [name for name in names if names.count(name) > 1]
        if duplicates:
            raise SyncError(f"Duplicate account names found: {', '.join(set(duplicates))}")

        # Validate each account
        for account in self.accounts:
            account.validate()


def load_accounts_from_json(filepath: Path) -> List[AccountConfig]:
    """
    Load accounts from JSON configuration file.

    Args:
        filepath: Path to accounts.json file

    Returns:
        List of AccountConfig instances

    Raises:
        SyncError: If file is invalid or missing required fields
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        if "accounts" not in data:
            raise SyncError("accounts.json missing 'accounts' key")

        if not isinstance(data["accounts"], list):
            raise SyncError("'accounts' must be a list")

        if not data["accounts"]:
            raise SyncError("'accounts' list is empty")

        accounts = [AccountConfig.from_dict(acc_data) for acc_data in data["accounts"]]
        return accounts

    except FileNotFoundError:
        raise SyncError(f"Accounts file not found: {filepath}")
    except json.JSONDecodeError as e:
        raise SyncError(f"Invalid JSON in accounts file: {e}")
    except Exception as e:
        raise SyncError(f"Failed to load accounts: {e}")


def load_account_from_env() -> AccountConfig:
    """
    Load single account from environment variables (legacy mode).

    Returns:
        AccountConfig instance

    Raises:
        SyncError: If required env vars are missing
    """
    # Load .env file if it exists
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    account = AccountConfig(
        name="default",
        goodreads_email=os.getenv("GOODREADS_EMAIL", ""),
        goodreads_password=os.getenv("GOODREADS_PASSWORD", ""),
        storygraph_email=os.getenv("STORYGRAPH_EMAIL", ""),
        storygraph_password=os.getenv("STORYGRAPH_PASSWORD", ""),
    )

    account.validate()
    return account


def load_config() -> Config:
    """
    Load configuration from accounts.json or environment variables.

    If /data/config/accounts.json exists, load multiple accounts from it.
    Otherwise, fall back to legacy single-account mode using env vars.

    Returns:
        Config instance with accounts and settings

    Raises:
        SyncError: If configuration is invalid
    """
    # Load .env file for global settings
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    # Try multi-account mode first
    accounts_file = Path("/data/config/accounts.json")
    if accounts_file.exists():
        accounts = load_accounts_from_json(accounts_file)
    else:
        # Fall back to single-account env var mode
        accounts = [load_account_from_env()]

    # Load global settings from env vars
    config = Config(
        accounts=accounts,
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        force_sync=os.getenv("FORCE_FULL_SYNC", "false").lower() == "true",
        max_sync_items=int(os.getenv("MAX_SYNC_ITEMS")) if os.getenv("MAX_SYNC_ITEMS") else None,
    )

    config.validate()
    return config
