"""Main entry point for Goodreads to StoryGraph sync."""

import logging
import sys
from playwright.sync_api import Browser, sync_playwright

from .config import AccountConfig, Config, load_config
from .exceptions import GoodreadsExportError, StateError, StoryGraphUploadError, SyncError
from .goodreads import GoodreadsClient
from .logging_setup import setup_logging
from .state import calculate_csv_hash, load_state, save_state, should_skip_upload
from .storygraph import StoryGraphClient
from .transform import count_books, validate_csv


def sync_account(account: AccountConfig, config: Config, browser: Browser, logger: logging.Logger) -> bool:
    """
    Sync a single account from Goodreads to StoryGraph.

    Args:
        account: Account configuration
        config: Global configuration
        browser: Playwright browser instance
        logger: Logger instance

    Returns:
        True if sync succeeded, False if failed
    """
    account_prefix = f"[{account.name}]"

    try:
        logger.info("=" * 60)
        logger.info(f"{account_prefix} Starting sync")
        logger.info("=" * 60)

        # Display current state
        try:
            state = load_state(account.name)
            if state:
                logger.info(f"{account_prefix} Last sync: {state['last_sync_timestamp']}")
                logger.info(f"{account_prefix} Last book count: {state['last_book_count']}")
        except StateError as e:
            logger.warning(f"{account_prefix} Could not load state: {e}")

        # Step 1: Export from Goodreads
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 1: Export from Goodreads")
        logger.info("-" * 60)

        goodreads_client = GoodreadsClient(
            browser,
            account.goodreads_email,
            account.goodreads_password,
            account.name
        )

        goodreads_client.login()
        csv_path = goodreads_client.export_library()
        goodreads_client.close()

        logger.info(f"{account_prefix} Export complete: {csv_path}")

        # Step 2: Validate CSV
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 2: Validate CSV")
        logger.info("-" * 60)

        validate_csv(csv_path)
        book_count = count_books(csv_path)
        logger.info(f"{account_prefix} CSV validated: {book_count} books found")

        # Apply MAX_SYNC_ITEMS limit if set
        if config.max_sync_items:
            if book_count > config.max_sync_items:
                logger.warning(
                    f"{account_prefix} MAX_SYNC_ITEMS set to {config.max_sync_items}, "
                    f"but CSV has {book_count} books. This may cause issues with upload."
                )

        # Step 3: Check if upload needed
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 3: Check if upload needed")
        logger.info("-" * 60)

        skip_upload, reason = should_skip_upload(csv_path, account.name, config.force_sync)

        if skip_upload:
            logger.info(f"{account_prefix} Skipping upload: {reason}")
            logger.info("=" * 60)
            logger.info(f"{account_prefix} Sync complete (no upload needed)")
            logger.info("=" * 60)
            return True

        logger.info(f"{account_prefix} Upload needed: {reason}")

        # Step 4: Upload to StoryGraph
        if config.dry_run:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} DRY RUN: Skipping upload to StoryGraph")
            logger.info("-" * 60)
        else:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 4: Upload to StoryGraph")
            logger.info("-" * 60)

            storygraph_client = StoryGraphClient(
                browser,
                account.storygraph_email,
                account.storygraph_password,
                account.name
            )

            storygraph_client.login()
            storygraph_client.upload_csv(csv_path)
            storygraph_client.close()

            logger.info(f"{account_prefix} Upload complete")

            # Step 5: Update state
            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 5: Update state")
            logger.info("-" * 60)

            csv_hash = calculate_csv_hash(csv_path)
            save_state(csv_hash, book_count, account.name)

            logger.info(f"{account_prefix} State updated successfully")

        logger.info("=" * 60)
        logger.info(f"{account_prefix} Sync complete")
        logger.info("=" * 60)
        return True

    except GoodreadsExportError as e:
        logger.error(f"{account_prefix} Goodreads export failed: {e}")
        return False
    except StoryGraphUploadError as e:
        logger.error(f"{account_prefix} StoryGraph upload failed: {e}")
        return False
    except StateError as e:
        logger.error(f"{account_prefix} State error: {e}")
        return False
    except Exception as e:
        logger.exception(f"{account_prefix} Unexpected error: {e}")
        return False


def main() -> int:
    """
    Main sync workflow supporting multiple accounts.

    Returns:
        Exit code (0 if all accounts succeeded, 1 if any failed)
    """
    logger = None
    try:
        # Load configuration
        config = load_config()

        # Setup logging
        logger, run_log_path = setup_logging(config.log_level)
        logger.info("=" * 60)
        logger.info("Starting Goodreads → StoryGraph sync")
        logger.info(f"Run log: {run_log_path}")
        logger.info(f"Accounts to sync: {len(config.accounts)}")
        logger.info("=" * 60)

        if config.dry_run:
            logger.info("DRY RUN MODE - Will export but not upload")

        if config.force_sync:
            logger.info("FORCE SYNC MODE - Will upload even if unchanged")

        # Initialize Playwright
        logger.info("Initializing browser")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=config.headless)

            try:
                # Sync each account
                results = {}
                for account in config.accounts:
                    success = sync_account(account, config, browser, logger)
                    results[account.name] = success

                # Summary
                logger.info("")
                logger.info("=" * 60)
                logger.info("SYNC SUMMARY")
                logger.info("=" * 60)

                successful = [name for name, success in results.items() if success]
                failed = [name for name, success in results.items() if not success]

                logger.info(f"Total accounts: {len(results)}")
                logger.info(f"Successful: {len(successful)}")
                if successful:
                    for name in successful:
                        logger.info(f"  ✓ {name}")

                logger.info(f"Failed: {len(failed)}")
                if failed:
                    for name in failed:
                        logger.error(f"  ✗ {name}")

                logger.info("=" * 60)

                # Return 0 only if all succeeded
                return 0 if not failed else 1

            finally:
                browser.close()

    except SyncError as e:
        if logger:
            logger.error(f"Configuration error: {e}")
        else:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if logger:
            logger.exception(f"Unexpected error: {e}")
        else:
            print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
