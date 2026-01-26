"""Goodreads client for exporting library data."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, Page

from .config import get_data_path
from .exceptions import GoodreadsExportError, PlaywrightError
from .selectors import GoodreadsSelectors


logger = logging.getLogger("sync.goodreads")


class GoodreadsClient:
    """Client for automating Goodreads library export."""

    def __init__(self, browser: Browser, email: str, password: str, account_name: str = "default"):
        """
        Initialize Goodreads client.

        Args:
            browser: Playwright browser instance
            email: Goodreads login email
            password: Goodreads login password
            account_name: Unique account identifier for state isolation
        """
        self.browser = browser
        self.email = email
        self.password = password
        self.account_name = account_name
        self.page: Optional[Page] = None
        self.storage_state_path = get_data_path() / "state" / f"playwright_storage_goodreads_{account_name}.json"

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

            # Click "Sign in with email" button if present (new Goodreads UI)
            try:
                # Try multiple selectors for the email login button
                sign_in_email_btn = self.page.locator('text="Sign in with email"')
                if sign_in_email_btn.count() > 0:
                    logger.info("Clicking 'Sign in with email' button")
                    sign_in_email_btn.first.click()
                    self.page.wait_for_timeout(2000)  # Wait for redirect
                    self.page.wait_for_load_state("networkidle")
            except Exception as e:
                logger.debug(f"No 'Sign in with email' button found, proceeding with direct login: {e}")

            # Check if we were auto-logged in via Amazon SSO
            if self._is_logged_in():
                logger.info("Already logged in via Amazon SSO")
                self._save_storage_state()
                return

            # Fill login form if we're on Amazon login page
            logger.info("Entering credentials")
            try:
                self.page.fill(GoodreadsSelectors.LOGIN_EMAIL_INPUT, self.email, timeout=10000)
                self.page.fill(GoodreadsSelectors.LOGIN_PASSWORD_INPUT, self.password, timeout=10000)

                # Submit form
                self.page.click(GoodreadsSelectors.LOGIN_SUBMIT_BUTTON)
                self.page.wait_for_load_state("networkidle")

                # Verify login success
                if not self._is_logged_in():
                    self._save_screenshot("login_failed")
                    raise GoodreadsExportError("Login verification failed")

                logger.info("Login successful")
                self._save_storage_state()
            except Exception as form_error:
                # If form filling fails, check if we're actually logged in
                if self._is_logged_in():
                    logger.info("Login succeeded via redirect")
                    self._save_storage_state()
                else:
                    raise form_error

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

            # Set up download path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_path = get_data_path() / "artifacts" / f"goodreads_export_{self.account_name}_{timestamp}.csv"

            # Check if a download link already exists
            download_link = self.page.locator(GoodreadsSelectors.DOWNLOAD_LINK)
            if download_link.count() > 0:
                logger.info("Found existing export download link")
            else:
                # Check if export button is enabled and click it
                export_btn = self.page.locator(GoodreadsSelectors.EXPORT_BUTTON)
                if export_btn.count() > 0:
                    if export_btn.is_enabled():
                        logger.info("Triggering export")
                        export_btn.click()
                    else:
                        logger.info("Export already in progress, waiting...")

                # Wait for download link to appear (export can take a while for large libraries)
                logger.info("Waiting for export to complete...")
                download_link = self.page.locator(GoodreadsSelectors.DOWNLOAD_LINK)
                download_link.wait_for(state="visible", timeout=120000)

            # Download the file
            logger.info("Downloading export file")
            with self.page.expect_download(timeout=60000) as download_info:
                download_link.first.click()

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
