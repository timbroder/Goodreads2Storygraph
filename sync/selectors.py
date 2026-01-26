"""Centralized CSS/XPath selectors for Goodreads and StoryGraph."""


class GoodreadsSelectors:
    """Selectors for Goodreads website."""

    # Login page - initial view with SSO options
    SIGN_IN_WITH_EMAIL_BUTTON = 'button:has-text("Sign in with email"), a:has-text("Sign in with email")'

    # Login page - email/password form (after clicking Sign in with email)
    LOGIN_EMAIL_INPUT = 'input[name="user[email]"], input#ap_email, input#user_email'
    LOGIN_PASSWORD_INPUT = 'input[name="user[password]"], input#ap_password, input#user_password'
    LOGIN_SUBMIT_BUTTON = 'button[type="submit"], input[type="submit"]'

    # Export page
    EXPORT_URL = "https://www.goodreads.com/review/import"
    EXPORT_BUTTON = 'button.js-LibraryExport, button:has-text("Export Library")'
    EXPORT_IN_PROGRESS = 'button.js-LibraryExport[disabled], :text("Exporting library")'
    DOWNLOAD_LINK = '#exportFile a[href*=".csv"], .fileList a[href*="export"]'

    # Verification - updated for current Goodreads UI
    # "My Books" nav link is a reliable indicator of being logged in
    LOGGED_IN_INDICATOR = 'a:has-text("My Books"), .siteHeader__personalNav, .profileMenu, a[href*="/user/show"]'


class StoryGraphSelectors:
    """Selectors for TheStoryGraph website."""

    # Login page
    LOGIN_URL = "https://app.thestorygraph.com/users/sign_in"
    LOGIN_EMAIL_INPUT = 'input[name="user[email]"], input#user_email'
    LOGIN_PASSWORD_INPUT = 'input[name="user[password]"], input#user_password'
    LOGIN_SUBMIT_BUTTON = 'button[type="submit"], input[type="submit"][value="Log in"]'

    # Import page
    IMPORT_URL = "https://app.thestorygraph.com/import-goodreads"
    FILE_INPUT = '#goodreads_export_csv, input[name="goodreads_export_csv"]'
    UPLOAD_BUTTON = 'button:has-text("Upload"), button:has-text("Import")'

    # Success indicators
    SUCCESS_MESSAGE = '.alert-success, .notice, :text("successfully"), :text("imported")'
    IMPORT_COMPLETE = ':text("Import complete"), :text("imported successfully")'

    # Verification - updated for current StoryGraph UI
    LOGGED_IN_INDICATOR = ':text("Signed in successfully"), :text("Hi again"), .user-menu, .profile-link, a[href="/users/sign_out"]'
