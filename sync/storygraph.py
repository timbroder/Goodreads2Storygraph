"""StoryGraph client for uploading library data."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, Page

from .exceptions import StoryGraphUploadError
from .selectors import StoryGraphSelectors


logger = logging.getLogger("sync.storygraph")


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
        self.storage_state_path = Path(f"/data/state/playwright_storage_storygraph_{account_name}.json")

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

            # Click upload button if needed
            try:
                upload_button = self.page.locator(StoryGraphSelectors.UPLOAD_BUTTON)
                if upload_button.count() > 0:
                    logger.info("Clicking upload button")
                    upload_button.click()
            except Exception:
                logger.debug("No explicit upload button found, file upload may be automatic")

            # Wait for success indication
            logger.info("Waiting for upload confirmation")
            self.page.wait_for_selector(
                StoryGraphSelectors.SUCCESS_MESSAGE,
                timeout=60000
            )

            logger.info("Upload successful")
            self._save_screenshot("upload_success")

        except Exception as e:
            self._save_screenshot("upload_failed")
            self._save_html("upload_failed")
            raise StoryGraphUploadError(f"Upload failed: {e}")

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
            screenshot_dir = Path(f"/data/artifacts/screenshots/{timestamp}")
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
            html_dir = Path(f"/data/artifacts/html/{timestamp}")
            html_dir.mkdir(parents=True, exist_ok=True)
            html_path = html_dir / f"{name}.html"
            html_path.write_text(self.page.content())
            logger.info(f"HTML saved: {html_path}")
        except Exception as e:
            logger.warning(f"Failed to save HTML: {e}")
