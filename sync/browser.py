"""Browser launch configuration with stealth settings.

Amazon's auth page blocks standard headless Chromium. This module
configures Playwright to be harder to detect as automated:
- Uses Chromium's "new" headless mode (--headless=new) which behaves
  identically to headed mode
- Sets a realistic user-agent string
- Disables automation-revealing flags (navigator.webdriver, etc.)
"""

import logging
from playwright.sync_api import Browser, Playwright

logger = logging.getLogger("sync.browser")

# Realistic Chrome user-agent (matches a real Chrome on macOS)
STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Chromium args to reduce bot detection fingerprint
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]


def launch_browser(playwright: Playwright, headless: bool = True) -> Browser:
    """Launch Chromium with stealth settings to avoid bot detection.

    When headless=True, uses Chromium's new headless mode which is
    much harder for sites like Amazon to detect.

    Args:
        playwright: Playwright instance
        headless: Whether to run headless

    Returns:
        Browser instance
    """
    args = list(STEALTH_ARGS)

    if headless:
        # Use "new" headless mode - behaves like headed but without a window
        args.append("--headless=new")
        logger.info("Launching browser in stealth headless mode")
    else:
        logger.info("Launching browser in headed mode")

    browser = playwright.chromium.launch(
        headless=False,  # We handle headless via --headless=new arg
        args=args,
    )

    return browser
