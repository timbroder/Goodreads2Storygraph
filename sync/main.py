"""Main entry point for Goodreads to StoryGraph sync."""

import logging
import sys
from playwright.sync_api import Browser, sync_playwright

from .config import AccountConfig, Config, load_config
from .exceptions import GoodreadsExportError, StateError, StoryGraphUploadError, SyncError
from .delta import compute_delta, load_goodreads_books
from .goodreads import GoodreadsClient
from .isbn_lookup import enrich_csv_with_isbns
from .library_state import LibraryDatabase
from .logging_setup import setup_logging
from .state import calculate_csv_hash, load_state, save_state
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
    database = LibraryDatabase()
    goodreads_client = None
    storygraph_client = None

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

        # Step 2b: Enrich ISBNs if enabled
        if config.enrich_isbns:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 2b: Enrich missing ISBNs")
            logger.info("-" * 60)
            books_without_isbn, isbns_found, cache_hits = enrich_csv_with_isbns(csv_path)
            if books_without_isbn > 0:
                logger.info(f"{account_prefix} Books without ISBN: {books_without_isbn}")
                logger.info(f"{account_prefix} ISBNs found: {isbns_found} ({cache_hits} from cache)")
            else:
                logger.info(f"{account_prefix} All books already have ISBNs")

        # Apply MAX_SYNC_ITEMS limit if set
        if config.max_sync_items:
            if book_count > config.max_sync_items:
                logger.warning(
                    f"{account_prefix} MAX_SYNC_ITEMS set to {config.max_sync_items}, "
                    f"but CSV has {book_count} books. The limit is not enforced in phase 1 delta sync."
                )

        # Step 3: Seed local StoryGraph baseline if needed
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 3: Seed local StoryGraph baseline")
        logger.info("-" * 60)

        current_books = database.get_books(account.name)
        if current_books:
            logger.info(f"{account_prefix} Local library database already seeded with {len(current_books)} books")
        else:
            logger.info(f"{account_prefix} Local library database is empty; seeding from StoryGraph")
            storygraph_client = StoryGraphClient(
                browser,
                account.storygraph_email,
                account.storygraph_password,
                account.name
            )
            storygraph_client.login()
            seeded_count = storygraph_client.seed_library(account.name, database)
            logger.info(f"{account_prefix} Seeded local StoryGraph baseline with {seeded_count} books")
            current_books = database.get_books(account.name)

        # Step 4: Compare Goodreads export with local baseline
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 4: Compute delta")
        logger.info("-" * 60)

        csv_hash = calculate_csv_hash(csv_path)
        previous_hash = database.get_metadata(account.name, "last_goodreads_hash")
        if previous_hash == csv_hash and not config.force_sync:
            logger.info(f"{account_prefix} Skipping sync: Goodreads export hash unchanged")
            logger.info("=" * 60)
            logger.info(f"{account_prefix} Sync complete (no changes detected)")
            logger.info("=" * 60)
            return True

        desired_books = load_goodreads_books(csv_path)
        plan = compute_delta(desired_books, current_books)
        logger.info(f"{account_prefix} Goodreads books in supported shelves: {len(desired_books)}")
        logger.info(f"{account_prefix} Books to add: {len(plan.additions)}")
        logger.info(f"{account_prefix} Books to update: {len(plan.updates)}")

        if plan.total_changes == 0:
            database.set_metadata(account.name, "last_goodreads_hash", csv_hash)
            database.set_metadata(account.name, "last_goodreads_book_count", str(book_count))
            save_state(csv_hash, book_count, account.name)
            logger.info(f"{account_prefix} No per-book changes needed")
            logger.info("=" * 60)
            logger.info(f"{account_prefix} Sync complete")
            logger.info("=" * 60)
            return True

        # Step 5: Apply delta to StoryGraph
        if config.dry_run:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} DRY RUN: Skipping StoryGraph writes")
            logger.info("-" * 60)
            logger.info(
                f"{account_prefix} Planned changes: {len(plan.additions)} additions, "
                f"{len(plan.updates)} updates"
            )
        else:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 5: Apply StoryGraph delta")
            logger.info("-" * 60)

            if storygraph_client is None:
                storygraph_client = StoryGraphClient(
                    browser,
                    account.storygraph_email,
                    account.storygraph_password,
                    account.name
                )
                storygraph_client.login()

            added, updated = storygraph_client.apply_delta(
                account.name,
                database,
                plan.additions,
                plan.updates,
            )
            logger.info(f"{account_prefix} Delta applied: {added} additions, {updated} updates")

            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 6: Update state")
            logger.info("-" * 60)

            database.set_metadata(account.name, "last_goodreads_hash", csv_hash)
            database.set_metadata(account.name, "last_goodreads_book_count", str(book_count))
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
    finally:
        if goodreads_client:
            goodreads_client.close()
        if storygraph_client:
            storygraph_client.close()


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

        if config.enrich_isbns:
            logger.info("ISBN ENRICHMENT - Will look up missing ISBNs via API")

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
