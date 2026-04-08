"""StoryGraph client for syncing individual books via browser automation."""

import logging
import random
import re
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, Page

from .exceptions import BookNotFoundError, BookSyncError, StoryGraphUploadError
from .models import BookRecord
from .paths import artifacts_dir, state_dir
from .selectors import StoryGraphSelectors


logger = logging.getLogger("sync.storygraph")


class StoryGraphClient:
    """Client for automating StoryGraph book operations."""

    def __init__(self, browser: Browser, email: str, password: str, account_name: str = "default"):
        self.browser = browser
        self.email = email
        self.password = password
        self.account_name = account_name
        self.page: Optional[Page] = None
        self.storage_state_path = state_dir() / f"playwright_storage_storygraph_{account_name}.json"

    def login(self) -> None:
        """Login to StoryGraph using stored session or credentials."""
        try:
            if self.storage_state_path.exists():
                logger.info("Using stored StoryGraph session")
                context = self.browser.new_context(storage_state=str(self.storage_state_path))
                self.page = context.new_page()
                self.page.goto("https://app.thestorygraph.com/")
                self.page.wait_for_timeout(2000)

                if self._is_logged_in():
                    logger.info("Stored session is valid")
                    return

                logger.info("Stored session expired, logging in with credentials")
                self.page.close()
                context.close()

            context = self.browser.new_context()
            self.page = context.new_page()

            logger.info("Navigating to StoryGraph login")
            self.page.goto(StoryGraphSelectors.LOGIN_URL)
            self.page.wait_for_load_state("networkidle")

            logger.info("Entering credentials")
            self.page.fill(StoryGraphSelectors.LOGIN_EMAIL_INPUT, self.email)
            self.page.fill(StoryGraphSelectors.LOGIN_PASSWORD_INPUT, self.password)

            self.page.click(StoryGraphSelectors.LOGIN_SUBMIT_BUTTON)
            self.page.wait_for_load_state("networkidle")

            if not self._is_logged_in():
                self._save_screenshot("login_failed")
                raise StoryGraphUploadError("Login verification failed")

            logger.info("Login successful")
            self._save_storage_state()

        except StoryGraphUploadError:
            raise
        except Exception as e:
            self._save_screenshot("login_error")
            raise StoryGraphUploadError(f"Login failed: {e}")

    def upload_csv(self, csv_path: str) -> None:
        """Upload CSV file to StoryGraph (deprecated — use add_book instead)."""
        warnings.warn(
            "upload_csv is deprecated. StoryGraph CSV import is broken. Use add_book() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        try:
            self.page.goto(StoryGraphSelectors.IMPORT_URL)
            self.page.wait_for_load_state("networkidle")

            file_input = self.page.locator(StoryGraphSelectors.FILE_INPUT)
            file_input.set_input_files(csv_path)

            try:
                upload_button = self.page.locator(StoryGraphSelectors.UPLOAD_BUTTON)
                if upload_button.count() > 0:
                    upload_button.click()
            except Exception:
                pass

            self.page.wait_for_selector(StoryGraphSelectors.SUCCESS_MESSAGE, timeout=60000)
            self._save_screenshot("upload_success")

        except Exception as e:
            self._save_screenshot("upload_failed")
            self._save_html("upload_failed")
            raise StoryGraphUploadError(f"Upload failed: {e}")

    def find_book(self, book: BookRecord) -> Optional[str]:
        """
        Search for a book on StoryGraph and return its UUID.

        Tries ISBN search first, falls back to title+author.

        Returns:
            StoryGraph book UUID, or None if not found.
        """
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        # Try ISBN search first
        isbn = book.search_isbn()
        if isbn:
            uuid = self._search_for_book(isbn)
            if uuid:
                return uuid
            logger.debug(f"ISBN search returned no results for '{book.title}', trying title+author")

        # Fall back to title + author search
        search_term = f"{book.title} {book.author}"
        uuid = self._search_for_book(search_term)
        if uuid:
            return uuid

        return None

    def _search_for_book(self, search_term: str) -> Optional[str]:
        """Execute a search on StoryGraph and return the first result's UUID."""
        url = f"{StoryGraphSelectors.BROWSE_URL}?search_term={search_term}"
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)  # Extra wait for Turbo rendering

        book_panes = self.page.locator(StoryGraphSelectors.SEARCH_RESULTS_BOOK_PANE)
        if book_panes.count() == 0:
            return None

        # Get the first result's UUID
        first_pane = book_panes.first
        uuid = first_pane.get_attribute(StoryGraphSelectors.BOOK_PANE_DATA_ID)
        return uuid

    def add_book(self, book: BookRecord) -> bool:
        """
        Add or update a single book on StoryGraph with full metadata.

        Args:
            book: BookRecord with the book's metadata

        Returns:
            True if successful

        Raises:
            BookNotFoundError: If book cannot be found on StoryGraph
            BookSyncError: If metadata operations fail
        """
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        logger.info(f"Syncing: {book.title} by {book.author}")

        # Step 1: Find the book
        uuid = self.find_book(book)
        if not uuid:
            raise BookNotFoundError(
                f"Could not find '{book.title}' by {book.author} on StoryGraph"
            )
        logger.debug(f"Found book UUID: {uuid}")

        try:
            # Step 2: Set shelf (this also adds the book to library if not already there)
            self._set_shelf(uuid, book.storygraph_shelf())

            # Step 3: Set rating (if non-zero)
            if book.my_rating > 0:
                self._set_rating(uuid, book.my_rating)

            # Step 4: Set read dates (if available and shelf is "read")
            if book.date_read and book.exclusive_shelf == "read":
                self._set_dates(uuid, book.date_read)

            # Step 5: Set review (if non-empty)
            if book.my_review:
                self._set_review(uuid, book.my_review, book.my_rating)

            logger.info(f"Successfully synced: {book.title}")
            return True

        except BookSyncError:
            raise
        except Exception as e:
            self._save_screenshot(f"sync_failed_{uuid[:8]}")
            raise BookSyncError(f"Failed to sync '{book.title}': {e}")

    def _set_shelf(self, uuid: str, shelf: str) -> None:
        """Navigate to book page and set the shelf."""
        book_url = f"{StoryGraphSelectors.BOOK_PAGE_URL}/{uuid}"
        self.page.goto(book_url)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)

        # Map our shelf name to what StoryGraph uses in button text
        shelf_button_text = {
            "to read": "to read",
            "read": "read",
            "currently reading": "currently reading",
            "did not finish": "did not finish",
        }
        target = shelf_button_text.get(shelf, "to read")

        # Check if already on the correct shelf
        # StoryGraph shows "Book marked as {shelf}" for the current status button
        already_on_shelf = self.page.locator(f'button:has-text("Book marked as {target}")').first
        try:
            if already_on_shelf.count() > 0 and already_on_shelf.is_visible():
                logger.debug(f"Book already on shelf: {shelf}")
                return
        except Exception:
            pass

        # Case 1: Book is already in library (has a status button + chevron dropdown)
        # Click the chevron to open dropdown, then click "Mark book as {target}"
        try:
            # Find the chevron dropdown toggle (small button next to the status button)
            # It's identified by being near the status and having no meaningful text
            chevron = self.page.locator('button:has-text("Book marked as")').locator("xpath=following-sibling::button").first
            if chevron.count() > 0 and chevron.is_visible():
                chevron.click()
                self.page.wait_for_timeout(500)

                # Click the shelf option in the dropdown
                mark_button = self.page.locator(f'button:has-text("Mark book as {target}")').first
                if mark_button.count() > 0 and mark_button.is_visible():
                    mark_button.click()
                    self.page.wait_for_timeout(1500)
                    logger.debug(f"Changed shelf to: {shelf}")
                    return

            # Also try "Mark as finished" shortcut for "read"
            if shelf == "read":
                finished_btn = self.page.locator('button:has-text("Mark as finished")').first
                if finished_btn.count() > 0 and finished_btn.is_visible():
                    finished_btn.click()
                    self.page.wait_for_timeout(1500)
                    logger.debug("Marked as finished (read)")
                    return
        except Exception as e:
            logger.debug(f"Dropdown approach failed: {e}")

        # Case 2: Book is NOT in library yet (has "Add to your To-Read Pile" button)
        try:
            add_button = self.page.locator('button:has-text("Add to your To-Read Pile")').first
            if add_button.count() > 0 and add_button.is_visible():
                if shelf == "to read":
                    # Just click it directly
                    add_button.click()
                    self.page.wait_for_timeout(1500)
                    logger.debug("Added to To-Read Pile")
                    return
                else:
                    # Need to use the dropdown next to it to pick a different shelf
                    # The chevron is the sibling button
                    chevron = add_button.locator("xpath=following-sibling::button").first
                    if chevron.count() > 0:
                        chevron.click()
                        self.page.wait_for_timeout(500)
                        option = self.page.locator(f'button:has-text("{target}")').first
                        if option.count() > 0 and option.is_visible():
                            option.click()
                            self.page.wait_for_timeout(1500)
                            logger.debug(f"Added to shelf: {shelf}")
                            return

                    # Fallback: add to to-read first, then change shelf
                    add_button.click()
                    self.page.wait_for_timeout(1500)
                    logger.debug("Added to To-Read, will change shelf next")
                    # Reload and change shelf
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle")
                    self._set_shelf(uuid, shelf)
                    return
        except Exception as e:
            logger.debug(f"Add-to-library approach failed: {e}")

        logger.warning(f"Could not set shelf to '{shelf}' — book may already be on correct shelf")

    def _set_rating(self, uuid: str, rating: int) -> None:
        """Navigate to review page and set star rating."""
        if rating < 1 or rating > 5:
            return

        review_url = f"{StoryGraphSelectors.REVIEW_URL}?book_id={uuid}"
        self.page.goto(review_url)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(500)

        try:
            # Set integer part of rating
            int_select = self.page.locator(StoryGraphSelectors.RATING_INTEGER_SELECT)
            if int_select.count() > 0:
                int_select.select_option(str(rating))
                logger.debug(f"Set rating to {rating}")
            else:
                logger.warning("Rating integer select not found")
        except Exception as e:
            logger.warning(f"Could not set rating: {e}")

    def _set_review(self, uuid: str, review_text: str, rating: int = 0) -> None:
        """Set review text on the review page. Navigates to review page if not already there."""
        if not review_text:
            return

        # Navigate to review page if we're not already there
        current_url = self.page.url
        expected_url = f"{StoryGraphSelectors.REVIEW_URL}?book_id={uuid}"
        if "reviews/new" not in current_url or uuid not in current_url:
            self.page.goto(expected_url)
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(500)

            # Re-set rating if we navigated away
            if rating > 0:
                try:
                    self.page.locator(StoryGraphSelectors.RATING_INTEGER_SELECT).select_option(str(rating))
                except Exception:
                    pass

        try:
            # Find the contenteditable editor
            editor = self.page.locator(StoryGraphSelectors.REVIEW_EDITOR).first
            if editor.count() > 0:
                editor.click()
                editor.fill(review_text)
                logger.debug("Set review text")
            else:
                logger.warning("Review editor not found")
                return

            # Submit the review
            submit = self.page.locator(StoryGraphSelectors.REVIEW_SUBMIT).first
            if submit.count() > 0:
                submit.click()
                self.page.wait_for_timeout(2000)
                logger.debug("Submitted review")
        except Exception as e:
            logger.warning(f"Could not set review: {e}")

    def _set_dates(self, uuid: str, date_read: str) -> None:
        """Navigate to read history page and set finish date."""
        if not date_read:
            return

        # Parse the date (Goodreads format: YYYY/MM/DD or YYYY-MM-DD)
        try:
            date_read_clean = date_read.replace("/", "-").strip()
            parts = date_read_clean.split("-")
            if len(parts) != 3:
                logger.warning(f"Cannot parse date: {date_read}")
                return
            year, month, day = parts[0], str(int(parts[1])), str(int(parts[2]))
        except (ValueError, IndexError):
            logger.warning(f"Cannot parse date: {date_read}")
            return

        history_url = f"{StoryGraphSelectors.READ_INSTANCES_URL}?book_id={uuid}"
        self.page.goto(history_url)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(500)

        try:
            # Set finish date fields
            finish_day = self.page.locator(StoryGraphSelectors.READ_FINISH_DAY)
            finish_month = self.page.locator(StoryGraphSelectors.READ_FINISH_MONTH)
            finish_year = self.page.locator(StoryGraphSelectors.READ_FINISH_YEAR)

            if finish_day.count() > 0:
                finish_day.select_option(day)
                finish_month.select_option(month)
                finish_year.select_option(year)
                logger.debug(f"Set finish date: {year}-{month}-{day}")

                # Submit the form
                submit = self.page.locator(StoryGraphSelectors.READ_HISTORY_SUBMIT).first
                if submit.count() > 0 and submit.is_visible():
                    submit.click()
                    self.page.wait_for_timeout(1000)
                    logger.debug("Submitted read history")
            else:
                logger.warning("Read history date fields not found")
        except Exception as e:
            logger.warning(f"Could not set read dates: {e}")

    def wait_with_jitter(self, delay_min: float = 3.0, delay_max: float = 8.0) -> None:
        """Wait a random amount of time to avoid rate limiting."""
        delay = random.uniform(delay_min, delay_max)
        logger.debug(f"Waiting {delay:.1f}s before next operation")
        time.sleep(delay)

    def close(self) -> None:
        """Close browser context and page."""
        if self.page:
            try:
                self.page.context.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")

    def _is_logged_in(self) -> bool:
        """Check if currently logged in."""
        try:
            # First check: are we NOT on the sign-in page?
            if "sign_in" in self.page.url:
                return False

            # Try selector-based detection with longer timeout
            self.page.wait_for_selector(
                StoryGraphSelectors.LOGGED_IN_INDICATOR,
                timeout=10000
            )
            return True
        except Exception:
            # Fallback: check if page contains a greeting or profile nav
            try:
                content = self.page.content()
                if "Hi there," in content or "Hello," in content:
                    return True
                # Check for nav links that only appear when logged in
                if "/users/sign_out" in content:
                    return True
            except Exception:
                pass
            return False

    def _save_storage_state(self) -> None:
        """Save browser storage state for session reuse."""
        try:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            self.page.context.storage_state(path=str(self.storage_state_path))
            logger.debug("Storage state saved")
        except Exception as e:
            logger.warning(f"Failed to save storage state: {e}")

    def _save_screenshot(self, name: str) -> None:
        """Save screenshot for debugging."""
        if not self.page:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_dir = artifacts_dir() / "screenshots" / timestamp
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / f"{name}.png"
            self.page.screenshot(path=str(screenshot_path))
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")

    def _save_html(self, name: str) -> None:
        """Save page HTML for debugging."""
        if not self.page:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_dir = artifacts_dir() / "html" / timestamp
            html_dir.mkdir(parents=True, exist_ok=True)
            html_path = html_dir / f"{name}.html"
            html_path.write_text(self.page.content())
            logger.info(f"HTML saved: {html_path}")
        except Exception as e:
            logger.warning(f"Failed to save HTML: {e}")
