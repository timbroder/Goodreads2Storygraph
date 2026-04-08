"""StoryGraph client for uploading library data."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin
from typing import Optional

from playwright.sync_api import Browser, Page

from .config import get_data_path
from .exceptions import StoryGraphUploadError
from .library_state import BookRecord, LibraryDatabase, normalize_isbn, normalize_text
from .selectors import StoryGraphSelectors


logger = logging.getLogger("sync.storygraph")

STATUS_BUTTON_LABELS = {
    "to-read": "to read",
    "currently-reading": "currently reading",
    "read": "read",
    "did-not-finish": "did not finish",
}


class StoryGraphClient:
    """Client for automating StoryGraph CSV import."""

    def __init__(self, browser: Browser, email: str, password: str, account_name: str = "default"):
        """
        Initialize StoryGraph client.

        Args:
            browser: Playwright browser instance
            email: StoryGraph login email
            password: StoryGraph login password
            account_name: Unique account identifier for state isolation
        """
        self.browser = browser
        self.email = email
        self.password = password
        self.account_name = account_name
        self.page: Optional[Page] = None
        self.storage_state_path = get_data_path() / "state" / f"playwright_storage_storygraph_{account_name}.json"

    def login(self) -> None:
        """
        Login to StoryGraph using stored session or credentials.

        Raises:
            StoryGraphUploadError: If login fails
        """
        try:
            # Try to use stored session first
            if self.storage_state_path.exists():
                logger.info("Using stored StoryGraph session")
                context = self.browser.new_context(storage_state=str(self.storage_state_path))
                self.page = context.new_page()

                # Verify session is still valid
                self.page.goto("https://app.thestorygraph.com/")
                self.page.wait_for_timeout(2000)

                if self._is_logged_in():
                    logger.info("Stored session is valid")
                    return

                logger.info("Stored session expired, logging in with credentials")
                self.page.close()
                context.close()

            # Fresh login
            context = self.browser.new_context()
            self.page = context.new_page()

            logger.info("Navigating to StoryGraph login")
            self.page.goto(StoryGraphSelectors.LOGIN_URL)
            self.page.wait_for_load_state("networkidle")

            # Fill login form
            logger.info("Entering credentials")
            self.page.fill(StoryGraphSelectors.LOGIN_EMAIL_INPUT, self.email)
            self.page.fill(StoryGraphSelectors.LOGIN_PASSWORD_INPUT, self.password)

            # Submit form
            self.page.click(StoryGraphSelectors.LOGIN_SUBMIT_BUTTON)
            self.page.wait_for_load_state("networkidle")

            # Verify login success
            if not self._is_logged_in():
                self._save_screenshot("login_failed")
                raise StoryGraphUploadError("Login verification failed")

            logger.info("Login successful")
            self._save_storage_state()

        except Exception as e:
            self._save_screenshot("login_error")
            raise StoryGraphUploadError(f"Login failed: {e}")

    def upload_csv(self, csv_path: str) -> None:
        """
        Upload CSV file to StoryGraph and verify success.

        Args:
            csv_path: Path to the CSV file to upload

        Raises:
            StoryGraphUploadError: If upload fails
        """
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        try:
            logger.info("Navigating to import page")
            self.page.goto(StoryGraphSelectors.IMPORT_URL)
            self.page.wait_for_load_state("networkidle")

            # Upload file
            logger.info(f"Uploading CSV: {csv_path}")
            file_input = self.page.locator(StoryGraphSelectors.FILE_INPUT)
            file_input.set_input_files(csv_path)

            # Find and click the submit/import button
            logger.info("Looking for submit button")
            submit_button = self.page.locator('input[type="submit"], button[type="submit"], button:has-text("Import"), button:has-text("Submit")')
            if submit_button.count() > 0:
                logger.info("Clicking submit button")
                self._save_screenshot("before_submit")
                submit_button.first.click()

                # Wait for the page to process - button may show "Submitting..."
                self.page.wait_for_timeout(3000)
                self._save_screenshot("after_submit")

                # StoryGraph import is asynchronous - it queues the import
                # Check for either success message or "submitted" confirmation
                logger.info("Waiting for submission confirmation")
                try:
                    # Wait for any indication that submission was accepted
                    self.page.wait_for_selector(
                        ':text("queued"), :text("submitted"), :text("will receive an email"), :text("processing"), .alert-success, .notice',
                        timeout=30000
                    )
                    logger.info("Import submitted successfully (processing asynchronously)")
                except Exception:
                    # If no specific message, check if the button changed state
                    logger.info("No explicit confirmation, checking page state")
                    self._save_screenshot("submission_state")
            else:
                logger.warning("No submit button found")

            self._save_screenshot("upload_complete")

        except Exception as e:
            self._save_screenshot("upload_failed")
            self._save_html("upload_failed")
            raise StoryGraphUploadError(f"Upload failed: {e}")

    def seed_library(self, account_name: str, database: LibraryDatabase) -> int:
        """
        Scrape the current StoryGraph library and use it as the local baseline.

        Args:
            account_name: Unique account identifier
            database: Local SQLite wrapper

        Returns:
            Number of books stored for the account
        """
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        username = self.get_username()
        logger.info(f"Resolved StoryGraph username: {username}")

        books: dict[str, BookRecord] = {}

        for status, relative_path in (
            ("to-read", f"/to-read/{username}"),
            ("currently-reading", f"/currently-reading/{username}"),
            ("read", f"/books-read/{username}"),
        ):
            logger.info(f"Seeding StoryGraph status '{status}'")
            for book in self._scrape_status_page(relative_path, status):
                books[book.book_key] = book

        dnf_path = self._resolve_dnf_path(username)
        if dnf_path:
            logger.info("Seeding StoryGraph status 'did-not-finish'")
            for book in self._scrape_status_page(dnf_path, "did-not-finish"):
                books[book.book_key] = book
        else:
            logger.warning("Could not resolve StoryGraph DNF list; continuing without it")

        count = database.replace_books(account_name, books.values(), source="storygraph_seed")
        database.set_metadata(account_name, "storygraph_username", username)
        database.set_metadata(account_name, "storygraph_seeded_at", datetime.utcnow().isoformat())
        return count

    def apply_delta(self, account_name: str, database: LibraryDatabase, additions: list[BookRecord], updates: list[BookRecord]) -> tuple[int, int]:
        """
        Apply Goodreads delta changes to StoryGraph and update the local database.

        Args:
            account_name: Unique account identifier
            database: Local SQLite wrapper
            additions: Books missing from StoryGraph baseline
            updates: Books whose statuses changed in Goodreads

        Returns:
            Tuple of (added_count, updated_count)
        """
        added = 0
        updated = 0

        for book in additions:
            final_record = self._apply_book_status(book)
            database.upsert_book(account_name, final_record)
            added += 1

        for book in updates:
            final_record = self._apply_book_status(book)
            database.upsert_book(account_name, final_record)
            updated += 1

        return added, updated

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
            self.page.wait_for_selector(
                StoryGraphSelectors.LOGGED_IN_INDICATOR,
                timeout=5000
            )
            return True
        except Exception:
            return False

    def get_username(self) -> str:
        """Resolve the current StoryGraph username from the authenticated UI."""
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        self.page.goto("https://app.thestorygraph.com/", wait_until="networkidle")
        content = self.page.content()
        for pattern in (
            r"/to-read/([A-Za-z0-9_]+)",
            r"/currently-reading/([A-Za-z0-9_]+)",
            r"/books-read/([A-Za-z0-9_]+)",
        ):
            match = re.search(pattern, content)
            if match:
                return match.group(1)

        raise StoryGraphUploadError("Could not determine StoryGraph username from page content")

    def _resolve_dnf_path(self, username: str) -> Optional[str]:
        """Try to resolve the dedicated DNF page from the read list."""
        if not self.page:
            return None

        self.page.goto(f"https://app.thestorygraph.com/books-read/{username}", wait_until="networkidle")
        dnf_link = self.page.locator("a", has_text="DNF books").first
        try:
            href = dnf_link.get_attribute("href", timeout=5000)
        except Exception:
            href = None

        if not href:
            return None
        return urljoin("https://app.thestorygraph.com", href)

    def _scrape_status_page(self, url: str, status: str) -> list[BookRecord]:
        """Scrape one StoryGraph list page into normalized book records."""
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        absolute_url = url if url.startswith("http") else urljoin("https://app.thestorygraph.com", url)
        self.page.goto(absolute_url, wait_until="networkidle")
        self._set_results_per_page()
        self._scroll_until_stable()

        extracted = self.page.eval_on_selector_all(
            "a[href]",
            """
            anchors => {
              const clean = value => (value || "").replace(/\\s+/g, " ").trim();
              const ignoredHref = href => {
                return (
                  href.includes("/authors/") ||
                  href.includes("/series/") ||
                  href.includes("/stats/") ||
                  href.includes("/reviews/") ||
                  href.includes("/book_reviews/") ||
                  href.includes("/search")
                );
              };

              const findContainer = anchor => {
                let node = anchor;
                for (let i = 0; i < 8 && node; i += 1) {
                  const text = clean(node.innerText || "");
                  if (text.includes("ISBN/UID:") || text.includes("Expand dropdown menu") || text.includes("mark as owned")) {
                    return node;
                  }
                  node = node.parentElement;
                }
                return anchor.closest("article, li, section, div");
              };

              const seen = new Set();
              const books = [];

              for (const anchor of anchors) {
                const href = anchor.getAttribute("href") || "";
                const title = clean(anchor.textContent || "");
                if (!href || !title || title.length < 2 || ignoredHref(href)) {
                  continue;
                }

                const container = findContainer(anchor);
                if (!container) {
                  continue;
                }

                const text = clean(container.innerText || "");
                if (!text.includes("ISBN/UID:")) {
                  continue;
                }

                const candidateAnchors = [...container.querySelectorAll("a[href]")];
                const authorAnchor = candidateAnchors.find(candidate => {
                  if (candidate === anchor) {
                    return false;
                  }
                  const candidateHref = candidate.getAttribute("href") || "";
                  const candidateText = clean(candidate.textContent || "");
                  return candidateText && !ignoredHref(candidateHref) && candidateText !== title;
                });

                const author = clean(authorAnchor ? authorAnchor.textContent || "" : "");
                const isbnMatch = text.match(/ISBN\\/UID:\\s*([^\\n]+)/i);
                const key = `${href}|${title}|${author}`;
                if (seen.has(key)) {
                  continue;
                }
                seen.add(key);

                books.push({
                  href,
                  title,
                  author,
                  isbn13: isbnMatch ? clean(isbnMatch[1]) : ""
                });
              }

              return books;
            }
            """,
        )

        books: dict[str, BookRecord] = {}
        for item in extracted:
            title = item.get("title", "").strip()
            author = item.get("author", "").strip()
            if not title or not author:
                continue

            url_value = item.get("href") or ""
            absolute_book_url = urljoin("https://app.thestorygraph.com", url_value)
            book = BookRecord(
                title=title,
                author=author,
                status=status,
                isbn13=normalize_isbn(item.get("isbn13")),
                storygraph_url=absolute_book_url,
                source="storygraph_seed",
            )
            books[book.book_key] = book

        logger.info(f"Scraped {len(books)} books from {absolute_url}")
        return list(books.values())

    def _set_results_per_page(self) -> None:
        """Prefer fewer pagination hops when scraping public list pages."""
        if not self.page:
            return

        for label in ("100 / page", "50 / page"):
            option = self.page.get_by_text(label, exact=False)
            try:
                if option.count() > 0:
                    option.first.click(timeout=3000)
                    self.page.wait_for_timeout(1000)
                    return
            except Exception:
                continue

    def _scroll_until_stable(self, max_rounds: int = 8) -> None:
        """Load list pages that use infinite scroll."""
        if not self.page:
            return

        previous_height = 0
        stable_rounds = 0

        for _ in range(max_rounds):
            current_height = self.page.evaluate("document.body.scrollHeight")
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(1200)

            if current_height == previous_height:
                stable_rounds += 1
                if stable_rounds >= 2:
                    break
            else:
                stable_rounds = 0

            previous_height = current_height

    def _apply_book_status(self, book: BookRecord) -> BookRecord:
        """Navigate to a StoryGraph book and set the requested status."""
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        book_url = book.storygraph_url or self._search_for_book(book)
        if not book_url:
            raise StoryGraphUploadError(f"Could not find StoryGraph match for '{book.title}' by {book.author}")

        self.page.goto(book_url, wait_until="networkidle")
        self._click_status_button(book.status)

        return BookRecord(
            title=book.title,
            author=book.author,
            status=book.status,
            isbn13=book.isbn13,
            book_key=book.book_key,
            goodreads_book_id=book.goodreads_book_id,
            storygraph_url=self.page.url,
            source="storygraph_sync",
        )

    def _search_for_book(self, book: BookRecord) -> Optional[str]:
        """Search StoryGraph and return the best candidate URL for a book."""
        if not self.page:
            return None

        queries = [book.isbn13] if book.isbn13 else []
        queries.append(f"{book.title} {book.author}")

        for query in queries:
            if not query:
                continue

            search_url = f"{StoryGraphSelectors.SEARCH_URL}?search_term={quote_plus(query)}"
            self.page.goto(search_url, wait_until="networkidle")

            candidates = self.page.eval_on_selector_all(
                "a[href]",
                """
                anchors => {
                  const clean = value => (value || "").replace(/\\s+/g, " ").trim();
                  const seen = new Set();
                  const results = [];

                  for (const anchor of anchors) {
                    const href = anchor.getAttribute("href") || "";
                    const title = clean(anchor.textContent || "");
                    if (!href || !title || href.includes("/search") || href.includes("/reviews/")) {
                      continue;
                    }

                    let node = anchor;
                    let container = null;
                    for (let i = 0; i < 8 && node; i += 1) {
                      const text = clean(node.innerText || "");
                      if (text.includes("ISBN/UID:") || text.includes("Expand dropdown menu")) {
                        container = node;
                        break;
                      }
                      node = node.parentElement;
                    }

                    if (!container) {
                      continue;
                    }

                    const text = clean(container.innerText || "");
                    const isbnMatch = text.match(/ISBN\\/UID:\\s*([^\\n]+)/i);
                    const candidateAnchors = [...container.querySelectorAll("a[href]")];
                    const authorAnchor = candidateAnchors.find(candidate => {
                      const candidateHref = candidate.getAttribute("href") || "";
                      const candidateText = clean(candidate.textContent || "");
                      return candidate !== anchor && candidateText && !candidateHref.includes("/reviews/");
                    });

                    const author = clean(authorAnchor ? authorAnchor.textContent || "" : "");
                    const key = `${href}|${title}|${author}`;
                    if (seen.has(key)) {
                      continue;
                    }
                    seen.add(key);

                    results.push({
                      href,
                      title,
                      author,
                      isbn13: isbnMatch ? clean(isbnMatch[1]) : ""
                    });
                  }

                  return results;
                }
                """,
            )

            matched_url = self._match_search_candidate(book, candidates)
            if matched_url:
                return matched_url

        return None

    def _match_search_candidate(self, book: BookRecord, candidates: list[dict[str, Any]]) -> Optional[str]:
        """Pick the strongest StoryGraph search result for a Goodreads book."""
        desired_title = normalize_text(book.title)
        desired_author = normalize_text(book.author)
        desired_isbn = normalize_isbn(book.isbn13)

        for candidate in candidates:
            candidate_isbn = normalize_isbn(candidate.get("isbn13"))
            if desired_isbn and candidate_isbn == desired_isbn:
                return urljoin("https://app.thestorygraph.com", candidate["href"])

        for candidate in candidates:
            candidate_title = normalize_text(candidate.get("title", ""))
            candidate_author = normalize_text(candidate.get("author", ""))
            if desired_title == candidate_title and desired_author == candidate_author:
                return urljoin("https://app.thestorygraph.com", candidate["href"])

        return None

    def _click_status_button(self, status: str) -> None:
        """Set a StoryGraph book's status using the visible action controls."""
        if not self.page:
            raise StoryGraphUploadError("Not logged in")

        label = STATUS_BUTTON_LABELS[status]

        direct_button = self.page.get_by_role("button", name=label)
        try:
            if direct_button.count() > 0:
                direct_button.first.click(timeout=5000)
                self.page.wait_for_timeout(1000)
                return
        except Exception:
            logger.debug(f"Direct status button not available for '{label}', trying menu flow")

        menu_button = self.page.get_by_text("Expand dropdown menu", exact=False)
        try:
            if menu_button.count() > 0:
                menu_button.first.click(timeout=5000)
                self.page.wait_for_timeout(500)
        except Exception as exc:
            raise StoryGraphUploadError(f"Could not open status menu for '{label}': {exc}")

        status_option = self.page.get_by_text(label, exact=False)
        try:
            status_option.first.click(timeout=5000)
            self.page.wait_for_timeout(1000)
        except Exception as exc:
            raise StoryGraphUploadError(f"Could not set StoryGraph status to '{label}': {exc}")

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
            screenshot_dir = get_data_path() / "artifacts" / "screenshots" / timestamp
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
            html_dir = get_data_path() / "artifacts" / "html" / timestamp
            html_dir.mkdir(parents=True, exist_ok=True)
            html_path = html_dir / f"{name}.html"
            html_path.write_text(self.page.content())
            logger.info(f"HTML saved: {html_path}")
        except Exception as e:
            logger.warning(f"Failed to save HTML: {e}")
