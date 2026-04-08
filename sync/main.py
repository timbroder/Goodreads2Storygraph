"""Main entry point for Goodreads to StoryGraph sync."""

import argparse
import logging
import sys
from playwright.sync_api import Browser, sync_playwright

from .config import AccountConfig, Config, load_config
from .exceptions import (
    BookNotFoundError,
    BookSyncError,
    GoodreadsExportError,
    StateError,
    StoryGraphUploadError,
    SyncError,
)
from .goodreads import GoodreadsClient
from .isbn_lookup import enrich_csv_with_isbns
from .logging_setup import setup_logging
from .state import (
    calculate_csv_hash,
    compute_delta,
    load_state,
    mark_book_failed,
    mark_book_synced,
    save_state,
    should_skip_upload,
)
from .storygraph import StoryGraphClient
from .transform import count_books, parse_csv_to_books, validate_csv


def sync_account(account: AccountConfig, config: Config, browser: Browser, logger: logging.Logger) -> bool:
    """
    Sync a single account from Goodreads to StoryGraph.

    Uses delta detection to find new/changed books, then syncs them
    individually via Playwright browser automation.

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
                logger.info(f"{account_prefix} Last sync: {state.get('last_sync_timestamp', 'unknown')}")
                logger.info(f"{account_prefix} Last book count: {state.get('last_book_count', 'unknown')}")
                synced_count = len(state.get("books", {}))
                failed_count = len(state.get("failed_books", {}))
                logger.info(f"{account_prefix} Books tracked: {synced_count} synced, {failed_count} failed")
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

        # Step 3: Fast-path check — skip if CSV completely unchanged
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 3: Check for changes")
        logger.info("-" * 60)

        skip, reason = should_skip_upload(csv_path, account.name, config.force_sync)
        if skip:
            logger.info(f"{account_prefix} Skipping sync: {reason}")
            logger.info("=" * 60)
            logger.info(f"{account_prefix} Sync complete (no changes)")
            logger.info("=" * 60)
            return True
        logger.info(f"{account_prefix} {reason}")

        # Step 4: Parse CSV and compute delta
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 4: Compute delta")
        logger.info("-" * 60)

        csv_books = parse_csv_to_books(csv_path)
        state = load_state(account.name)
        delta = compute_delta(csv_books, state, max_retries=config.max_retries)

        logger.info(f"{account_prefix} Delta: "
                     f"{len(delta.new_books)} new, "
                     f"{len(delta.changed_books)} changed, "
                     f"{delta.unchanged_count} unchanged, "
                     f"{len(delta.removed_book_ids)} removed (not synced), "
                     f"{len(delta.retryable_books)} retryable")

        if delta.removed_book_ids:
            logger.info(f"{account_prefix} Removed from Goodreads (kept on StoryGraph): "
                         f"{len(delta.removed_book_ids)} books")

        if not delta.has_changes and not config.force_sync:
            logger.info(f"{account_prefix} No books to sync")
            # Still update the CSV hash so fast-path works next time
            csv_hash = calculate_csv_hash(csv_path)
            save_state(csv_hash=csv_hash, book_count=book_count, account_name=account.name)
            logger.info("=" * 60)
            logger.info(f"{account_prefix} Sync complete (no book changes)")
            logger.info("=" * 60)
            return True

        # Step 5: Sync books to StoryGraph
        if config.dry_run:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} DRY RUN: Would sync {len(delta.sync_books)} books")
            logger.info("-" * 60)
            for book in delta.sync_books[:10]:
                logger.info(f"{account_prefix}   - {book.title} by {book.author} [{book.exclusive_shelf}]")
            if len(delta.sync_books) > 10:
                logger.info(f"{account_prefix}   ... and {len(delta.sync_books) - 10} more")
        else:
            logger.info("-" * 60)
            logger.info(f"{account_prefix} STEP 5: Sync {len(delta.sync_books)} books to StoryGraph")
            logger.info("-" * 60)

            storygraph_client = StoryGraphClient(
                browser,
                account.storygraph_email,
                account.storygraph_password,
                account.name
            )
            storygraph_client.login()

            synced = 0
            failed = 0
            books_to_sync = delta.sync_books

            # Respect max_sync_items limit
            if config.max_sync_items and len(books_to_sync) > config.max_sync_items:
                logger.info(f"{account_prefix} Limiting to {config.max_sync_items} books (of {len(books_to_sync)})")
                books_to_sync = books_to_sync[:config.max_sync_items]

            for i, book in enumerate(books_to_sync, 1):
                logger.info(f"{account_prefix} [{i}/{len(books_to_sync)}] {book.title}")
                try:
                    storygraph_client.add_book(book)
                    mark_book_synced(account.name, book.book_id, book.row_hash())
                    synced += 1
                except BookNotFoundError:
                    mark_book_failed(account.name, book.book_id, book.row_hash(), "not found")
                    failed += 1
                    logger.warning(f"{account_prefix} Not found on StoryGraph: {book.title}")
                except BookSyncError as e:
                    mark_book_failed(account.name, book.book_id, book.row_hash(), str(e))
                    failed += 1
                    logger.error(f"{account_prefix} Failed to sync: {book.title}: {e}")

                # Rate limiting delay (skip after last book)
                if i < len(books_to_sync):
                    storygraph_client.wait_with_jitter(config.sync_delay_min, config.sync_delay_max)

            storygraph_client.close()
            logger.info(f"{account_prefix} Sync results: {synced} synced, {failed} failed")

        # Step 6: Update state
        logger.info("-" * 60)
        logger.info(f"{account_prefix} STEP 6: Update state")
        logger.info("-" * 60)

        csv_hash = calculate_csv_hash(csv_path)
        save_state(csv_hash=csv_hash, book_count=book_count, account_name=account.name)
        logger.info(f"{account_prefix} State updated")

        logger.info("=" * 60)
        logger.info(f"{account_prefix} Sync complete")
        logger.info("=" * 60)
        return True

    except GoodreadsExportError as e:
        logger.error(f"{account_prefix} Goodreads export failed: {e}")
        return False
    except StoryGraphUploadError as e:
        logger.error(f"{account_prefix} StoryGraph error: {e}")
        return False
    except StateError as e:
        logger.error(f"{account_prefix} State error: {e}")
        return False
    except Exception as e:
        logger.exception(f"{account_prefix} Unexpected error: {e}")
        return False


def sync_from_csv(csv_path: str, account_name: str = "default") -> int:
    """
    Run the sync using a local Goodreads CSV, skipping the Goodreads export step.

    This is useful for local testing or when Goodreads login is broken.
    Reads StoryGraph credentials from config to perform the actual sync.
    """
    import os
    os.environ.setdefault("DRY_RUN", "false")

    try:
        config = load_config()
        logger, run_log_path = setup_logging(config.log_level)
        logger.info(f"Syncing from local CSV: {csv_path}")

        # Find the account
        account = None
        for acc in config.accounts:
            if acc.name == account_name:
                account = acc
                break
        if not account:
            account = config.accounts[0]
            logger.info(f"Using account: {account.name}")

        # Validate CSV
        validate_csv(csv_path)
        book_count = count_books(csv_path)
        logger.info(f"CSV validated: {book_count} books")

        # Check for changes
        skip, reason = should_skip_upload(csv_path, account.name, config.force_sync)
        if skip:
            logger.info(f"Skipping sync: {reason}")
            return 0
        logger.info(reason)

        # Compute delta
        csv_books = parse_csv_to_books(csv_path)
        state = load_state(account.name)
        delta = compute_delta(csv_books, state, max_retries=config.max_retries)

        logger.info(f"Delta: {len(delta.new_books)} new, "
                     f"{len(delta.changed_books)} changed, "
                     f"{delta.unchanged_count} unchanged, "
                     f"{len(delta.removed_book_ids)} removed, "
                     f"{len(delta.retryable_books)} retryable")

        if not delta.has_changes and not config.force_sync:
            logger.info("No books to sync")
            csv_hash = calculate_csv_hash(csv_path)
            save_state(csv_hash=csv_hash, book_count=book_count, account_name=account.name)
            return 0

        if config.dry_run:
            logger.info(f"DRY RUN: Would sync {len(delta.sync_books)} books")
            for book in delta.sync_books[:20]:
                logger.info(f"  - {book.title} by {book.author} [{book.exclusive_shelf}]")
            if len(delta.sync_books) > 20:
                logger.info(f"  ... and {len(delta.sync_books) - 20} more")
        else:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=config.headless)
                try:
                    storygraph_client = StoryGraphClient(
                        browser,
                        account.storygraph_email,
                        account.storygraph_password,
                        account.name
                    )
                    storygraph_client.login()

                    books_to_sync = delta.sync_books
                    if config.max_sync_items and len(books_to_sync) > config.max_sync_items:
                        logger.info(f"Limiting to {config.max_sync_items} books")
                        books_to_sync = books_to_sync[:config.max_sync_items]

                    synced = 0
                    failed = 0
                    for i, book in enumerate(books_to_sync, 1):
                        logger.info(f"[{i}/{len(books_to_sync)}] {book.title}")
                        try:
                            storygraph_client.add_book(book)
                            mark_book_synced(account.name, book.book_id, book.row_hash())
                            synced += 1
                        except BookNotFoundError:
                            mark_book_failed(account.name, book.book_id, book.row_hash(), "not found")
                            failed += 1
                            logger.warning(f"Not found: {book.title}")
                        except BookSyncError as e:
                            mark_book_failed(account.name, book.book_id, book.row_hash(), str(e))
                            failed += 1
                            logger.error(f"Failed: {book.title}: {e}")

                        if i < len(books_to_sync):
                            storygraph_client.wait_with_jitter(config.sync_delay_min, config.sync_delay_max)

                    storygraph_client.close()
                    logger.info(f"Results: {synced} synced, {failed} failed")
                finally:
                    browser.close()

        csv_hash = calculate_csv_hash(csv_path)
        save_state(csv_hash=csv_hash, book_count=book_count, account_name=account.name)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main sync workflow supporting multiple accounts.

    Returns:
        Exit code (0 if all accounts succeeded, 1 if any failed)
    """
    logger = None
    try:
        config = load_config()
        logger, run_log_path = setup_logging(config.log_level)

        logger.info("=" * 60)
        logger.info("Starting Goodreads → StoryGraph sync")
        logger.info(f"Run log: {run_log_path}")
        logger.info(f"Accounts to sync: {len(config.accounts)}")
        logger.info("=" * 60)

        if config.dry_run:
            logger.info("DRY RUN MODE - Will export and compute delta but not sync")
        if config.force_sync:
            logger.info("FORCE SYNC MODE - Will sync even if unchanged")

        if config.enrich_isbns:
            logger.info("ISBN ENRICHMENT - Will look up missing ISBNs via API")

        # Initialize Playwright
        logger.info("Initializing browser")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=config.headless)

            try:
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


def _load_storygraph_isbns(storygraph_csv: str) -> tuple[set, set]:
    """
    Parse a StoryGraph export CSV and return sets of ISBNs and lowercase titles.

    Returns:
        Tuple of (isbn_set, title_set)
    """
    import csv
    isbns = set()
    titles = set()
    with open(storygraph_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isbn = row.get("ISBN/UID", "").strip()
            title = row.get("Title", "").strip()
            if isbn:
                isbns.add(isbn)
            if title:
                titles.add(title.lower())
    return isbns, titles


def seed_state(goodreads_csv: str, storygraph_csv: str = None, account_name: str = "default") -> int:
    """
    Seed the state file by comparing Goodreads and StoryGraph exports.

    If a StoryGraph CSV is provided, only books found on both platforms
    (matched by ISBN or title) are marked as synced. Unmatched Goodreads
    books are left as "new" so they'll be synced on the next run.

    If no StoryGraph CSV is provided, ALL Goodreads books are marked as
    synced (use this only if you're sure everything is already on StoryGraph).

    Args:
        goodreads_csv: Path to a Goodreads CSV export
        storygraph_csv: Path to a StoryGraph CSV export (from /user-export)
        account_name: Account name to seed state for

    Returns:
        Exit code (0 on success, 1 on failure)
    """
    try:
        validate_csv(goodreads_csv)
        csv_books = parse_csv_to_books(goodreads_csv)
        csv_hash = calculate_csv_hash(goodreads_csv)

        # Load StoryGraph data for comparison if provided
        sg_isbns = set()
        sg_titles = set()
        if storygraph_csv:
            sg_isbns, sg_titles = _load_storygraph_isbns(storygraph_csv)
            print(f"StoryGraph export: {len(sg_isbns)} books with ISBN, {len(sg_titles)} total")

        # Build per-book state
        books_synced = {}
        books_new = []
        for book_id, book in csv_books.items():
            if storygraph_csv:
                # Check if this book exists on StoryGraph
                matched = False
                if book.isbn13 and book.isbn13 in sg_isbns:
                    matched = True
                elif book.isbn and book.isbn in sg_isbns:
                    matched = True
                elif book.title.lower() in sg_titles:
                    matched = True

                if matched:
                    books_synced[book_id] = {
                        "row_hash": book.row_hash(),
                        "last_synced": "seeded",
                        "status": "synced",
                    }
                else:
                    books_new.append(book)
            else:
                # No StoryGraph CSV — mark everything as synced
                books_synced[book_id] = {
                    "row_hash": book.row_hash(),
                    "last_synced": "seeded",
                    "status": "synced",
                }

        save_state(
            csv_hash=csv_hash,
            book_count=len(csv_books),
            account_name=account_name,
            books=books_synced,
            failed_books={},
        )

        print(f"\nGoodreads books: {len(csv_books)}")
        print(f"Marked as synced: {len(books_synced)}")
        print(f"New (will sync next run): {len(books_new)}")
        print(f"CSV hash: {csv_hash}")

        if books_new and len(books_new) <= 20:
            print(f"\nNew books to sync:")
            for b in books_new:
                print(f"  - {b.title} by {b.author}")
        elif books_new:
            print(f"\nFirst 20 new books to sync:")
            for b in books_new[:20]:
                print(f"  - {b.title} by {b.author}")
            print(f"  ... and {len(books_new) - 20} more")

        return 0

    except Exception as e:
        print(f"Error seeding state: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goodreads to StoryGraph sync")
    parser.add_argument(
        "--seed-state",
        metavar="GOODREADS_CSV",
        help="Seed state from a Goodreads CSV export",
    )
    parser.add_argument(
        "--storygraph-csv",
        metavar="STORYGRAPH_CSV",
        help="StoryGraph export CSV (from /user-export) for comparison. "
             "Only books found on both platforms are marked as synced.",
    )
    parser.add_argument(
        "--csv",
        metavar="CSV_PATH",
        help="Use a local Goodreads CSV instead of exporting from Goodreads. "
             "Skips the Goodreads login/export step entirely.",
    )
    parser.add_argument(
        "--account",
        default="default",
        help="Account name to operate on (default: 'default')",
    )

    args = parser.parse_args()

    if args.seed_state:
        sys.exit(seed_state(args.seed_state, args.storygraph_csv, args.account))
    elif args.csv:
        sys.exit(sync_from_csv(args.csv, args.account))
    else:
        sys.exit(main())
