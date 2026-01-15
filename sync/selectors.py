"""Centralized CSS/XPath selectors for Goodreads and StoryGraph."""


class GoodreadsSelectors:
    """Selectors for Goodreads website."""

    # Login page
    LOGIN_EMAIL_INPUT = 'input[name="user[email]"], input#ap_email'
    LOGIN_PASSWORD_INPUT = 'input[name="user[password]"], input#ap_password'
    LOGIN_SUBMIT_BUTTON = 'button[type="submit"], input[type="submit"]'

    # Export page
    EXPORT_URL = "https://www.goodreads.com/review/import"
    EXPORT_BUTTON = 'button:has-text("Export Library"), a:has-text("Export")'
    DOWNLOAD_LINK = 'a[href*="export"]'

    # Verification
    LOGGED_IN_INDICATOR = '.siteHeader__personalNav, .profileMenu'


class StoryGraphSelectors:
    """Selectors for TheStoryGraph website."""

    # Login page
    LOGIN_URL = "https://app.thestorygraph.com/users/sign_in"
    LOGIN_EMAIL_INPUT = 'input[name="user[email]"], input#user_email'
    LOGIN_PASSWORD_INPUT = 'input[name="user[password]"], input#user_password'
    LOGIN_SUBMIT_BUTTON = 'button[type="submit"], input[type="submit"][value="Log in"]'

    # Import page
    IMPORT_URL = "https://app.thestorygraph.com/import"
    FILE_INPUT = 'input[type="file"]'
    UPLOAD_BUTTON = 'button:has-text("Upload"), button:has-text("Import")'

    # Success indicators
    SUCCESS_MESSAGE = '.alert-success, .notice, text="successfully"'
    IMPORT_COMPLETE = 'text="Import complete", text="imported successfully"'

    # Verification
    LOGGED_IN_INDICATOR = '.user-menu, .profile-link, [data-user-menu]'
