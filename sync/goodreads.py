"""Goodreads client for exporting library data."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, Page

from .exceptions import GoodreadsExportError, PlaywrightError
from .selectors import GoodreadsSelectors


logger = logging.getLogger("sync.goodreads")


class GoodreadsClient:
    """Client for automating Goodreads library export."""

    def __init__(self, browser: Browser, email: str, password: str):
        """
        Initialize Goodreads client.

        Args:
            browser: Playwright browser instance
            email: Goodreads login email
            password: Goodreads login password
        """
        self.browser = browser
        self.email = email
        self.password = password
        self.page: Optional[Page] = None
        self.storage_state_path = Path("/data/state/playwright_storage_goodreads.json")

    def login(self) -> None:
        """
        Login to Goodreads using stored session or credentials.

        Raises:
            GoodreadsExportError: If login fails
        """
        try:
            # Try to use stored session first
            if self.storage_state_path.exists():
                logger.info("Using stored Goodreads session")
                context = self.browser.new_context(storage_state=str(self.storage_state_path))
                self.page = context.new_page()

                # Verify session is still valid
                self.page.goto("https://www.goodreads.com/")
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

            logger.info("Navigating to Goodreads login")
            self.page.goto("https://www.goodreads.com/user/sign_in")
            self.page.wait_for_load_state("networkidle")

            # Fill login form
            logger.info("Entering credentials")
            self.page.fill(GoodreadsSelectors.LOGIN_EMAIL_INPUT, self.email)
            self.page.fill(GoodreadsSelectors.LOGIN_PASSWORD_INPUT, self.password)

            # Submit form
            self.page.click(GoodreadsSelectors.LOGIN_SUBMIT_BUTTON)
            self.page.wait_for_load_state("networkidle")

            # Verify login success
            if not self._is_logged_in():
                self._save_screenshot("login_failed")
                raise GoodreadsExportError("Login verification failed")

            logger.info("Login successful")
            self._save_storage_state()

        except Exception as e:
            self._save_screenshot("login_error")
            raise GoodreadsExportError(f"Login failed: {e}")

    def export_library(self) -> str:
        """
        Export and download Goodreads library as CSV.

        Returns:
            Path to downloaded CSV file

        Raises:
            GoodreadsExportError: If export fails
        """
        if not self.page:
            raise GoodreadsExportError("Not logged in")

        try:
            logger.info("Navigating to export page")
            self.page.goto(GoodreadsSelectors.EXPORT_URL)
            self.page.wait_for_load_state("networkidle")

            # Set up download handler
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_path = Path(f"/data/artifacts/goodreads_export_{timestamp}.csv")

            logger.info("Triggering export")
            with self.page.expect_download(timeout=60000) as download_info:
                self.page.click(GoodreadsSelectors.EXPORT_BUTTON)

            download = download_info.value
            download.save_as(str(download_path))

            logger.info(f"Export downloaded to {download_path}")
            return str(download_path)

        except Exception as e:
            self._save_screenshot("export_failed")
            self._save_html("export_failed")
            raise GoodreadsExportError(f"Export failed: {e}")

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
                GoodreadsSelectors.LOGGED_IN_INDICATOR,
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
