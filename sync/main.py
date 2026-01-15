"""Main entry point for Goodreads to StoryGraph sync."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from .exceptions import GoodreadsExportError, StateError, StoryGraphUploadError, SyncError
from .goodreads import GoodreadsClient
from .logging_setup import setup_logging
from .state import load_state, save_state, should_skip_upload
from .storygraph import StoryGraphClient
from .transform import count_books, validate_csv


def get_config() -> dict:
    """
    Load configuration from environment variables.

    Returns:
        Dictionary with configuration values

    Raises:
        SyncError: If required env vars are missing
    """
    # Load .env file if it exists
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    config = {
        "goodreads_email": os.getenv("GOODREADS_EMAIL"),
        "goodreads_password": os.getenv("GOODREADS_PASSWORD"),
        "storygraph_email": os.getenv("STORYGRAPH_EMAIL"),
        "storygraph_password": os.getenv("STORYGRAPH_PASSWORD"),
        "headless": os.getenv("HEADLESS", "true").lower() == "true",
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "dry_run": os.getenv("DRY_RUN", "false").lower() == "true",
        "force_sync": os.getenv("FORCE_FULL_SYNC", "false").lower() == "true",
        "max_sync_items": os.getenv("MAX_SYNC_ITEMS"),
    }

    # Validate required fields
    required = [
        "goodreads_email",
        "goodreads_password",
        "storygraph_email",
        "storygraph_password",
    ]

    missing = [key for key in required if not config.get(key)]
    if missing:
        raise SyncError(f"Missing required environment variables: {', '.join(missing)}")

    return config


def main() -> int:
    """
    Main sync workflow.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Load configuration
        config = get_config()

        # Setup logging
        logger, run_log_path = setup_logging(config["log_level"])
        logger.info("=" * 60)
        logger.info("Starting Goodreads → StoryGraph sync")
        logger.info(f"Run log: {run_log_path}")
        logger.info("=" * 60)

        if config["dry_run"]:
            logger.info("DRY RUN MODE - Will export but not upload")

        if config["force_sync"]:
            logger.info("FORCE SYNC MODE - Will upload even if unchanged")

        # Display current state
        try:
            state = load_state()
            if state:
                logger.info(f"Last sync: {state['last_sync_timestamp']}")
                logger.info(f"Last book count: {state['last_book_count']}")
        except StateError as e:
            logger.warning(f"Could not load state: {e}")

        # Initialize Playwright
        logger.info("Initializing browser")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=config["headless"])

            try:
                # Step 1: Export from Goodreads
                logger.info("-" * 60)
                logger.info("STEP 1: Export from Goodreads")
                logger.info("-" * 60)

                goodreads_client = GoodreadsClient(
                    browser,
                    config["goodreads_email"],
                    config["goodreads_password"]
                )

                goodreads_client.login()
                csv_path = goodreads_client.export_library()
                goodreads_client.close()

                logger.info(f"Export complete: {csv_path}")

                # Step 2: Validate CSV
                logger.info("-" * 60)
                logger.info("STEP 2: Validate CSV")
                logger.info("-" * 60)

                validate_csv(csv_path)
                book_count = count_books(csv_path)
                logger.info(f"CSV validated: {book_count} books found")

                # Apply MAX_SYNC_ITEMS limit if set
                if config["max_sync_items"]:
                    max_items = int(config["max_sync_items"])
                    if book_count > max_items:
                        logger.warning(
                            f"MAX_SYNC_ITEMS set to {max_items}, but CSV has {book_count} books. "
                            "This may cause issues with upload. Consider removing the limit."
                        )

                # Step 3: Check if upload needed
                logger.info("-" * 60)
                logger.info("STEP 3: Check if upload needed")
                logger.info("-" * 60)

                skip_upload, reason = should_skip_upload(csv_path, config["force_sync"])

                if skip_upload:
                    logger.info(f"Skipping upload: {reason}")
                    logger.info("=" * 60)
                    logger.info("Sync complete (no upload needed)")
                    logger.info("=" * 60)
                    return 0

                logger.info(f"Upload needed: {reason}")

                # Step 4: Upload to StoryGraph
                if config["dry_run"]:
                    logger.info("-" * 60)
                    logger.info("DRY RUN: Skipping upload to StoryGraph")
                    logger.info("-" * 60)
                else:
                    logger.info("-" * 60)
                    logger.info("STEP 4: Upload to StoryGraph")
                    logger.info("-" * 60)

                    storygraph_client = StoryGraphClient(
                        browser,
                        config["storygraph_email"],
                        config["storygraph_password"]
                    )

                    storygraph_client.login()
                    storygraph_client.upload_csv(csv_path)
                    storygraph_client.close()

                    logger.info("Upload complete")

                    # Step 5: Update state
                    logger.info("-" * 60)
                    logger.info("STEP 5: Update state")
                    logger.info("-" * 60)

                    from .state import calculate_csv_hash
                    csv_hash = calculate_csv_hash(csv_path)
                    save_state(csv_hash, book_count)

                    logger.info("State updated successfully")

                logger.info("=" * 60)
                logger.info("Sync complete")
                logger.info("=" * 60)
                return 0

            finally:
                browser.close()

    except GoodreadsExportError as e:
        logger.error(f"Goodreads export failed: {e}")
        return 1
    except StoryGraphUploadError as e:
        logger.error(f"StoryGraph upload failed: {e}")
        return 1
    except StateError as e:
        logger.error(f"State error: {e}")
        return 1
    except SyncError as e:
        logger.error(f"Sync error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
