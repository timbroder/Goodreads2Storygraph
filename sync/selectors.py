"""Centralized CSS/XPath selectors for Goodreads and StoryGraph."""


class GoodreadsSelectors:
    """Selectors for Goodreads website."""

    # Sign-in landing page (provider selection)
    SIGN_IN_URL = "https://www.goodreads.com/user/sign_in"
    SIGN_IN_WITH_EMAIL = 'a:has-text("Sign in with email")'

    # Amazon auth page (after clicking "Sign in with email")
    LOGIN_EMAIL_INPUT = 'input[name="email"], input#ap_email'
    LOGIN_PASSWORD_INPUT = 'input[name="password"], input#ap_password'
    LOGIN_SUBMIT_BUTTON = 'input#signInSubmit, button[type="submit"], input[type="submit"]'

    # Export page
    EXPORT_URL = "https://www.goodreads.com/review/import"
    EXPORT_BUTTON = 'button:has-text("Export Library"), a:has-text("Export")'
    DOWNLOAD_LINK = 'a[href*="export"]'

    # Verification
    LOGGED_IN_INDICATOR = '.siteHeader__personalNav, .profileMenu, .dropdown--profileMenu'


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

    # Verification (logged-in homepage greeting or nav elements)
    LOGGED_IN_INDICATOR = 'text="Hi there,", text="Hello,", img[alt*="profile"], button:has-text("Open user menu")'

    # Search / Browse
    BROWSE_URL = "https://app.thestorygraph.com/browse"
    SEARCH_RESULTS_BOOK_PANE = ".book-pane"
    BOOK_PANE_DATA_ID = "data-book-id"
    BOOK_TITLE_LINK = ".book-title-author-and-series a"

    # Book page base URL (append UUID)
    BOOK_PAGE_URL = "https://app.thestorygraph.com/books"

    # Shelf buttons (used on both search results and book detail pages)
    SHELF_TO_READ_BUTTON = 'form.button_to button:has-text("to read")'
    SHELF_READ_BUTTON = 'form.button_to button:text-is("read")'
    SHELF_CURRENTLY_READING_BUTTON = 'form.button_to button:has-text("currently reading")'
    SHELF_DID_NOT_FINISH_BUTTON = 'form.button_to button:has-text("did not finish")'
    SHELF_DROPDOWN_TOGGLE = '.book-pane button[type="button"]:near(button:has-text("read"))'

    # Review page: /reviews/new?book_id={uuid}
    REVIEW_URL = "https://app.thestorygraph.com/reviews/new"
    RATING_INTEGER_SELECT = "select#stars_integer"
    RATING_DECIMAL_SELECT = "select#stars_decimal"
    REVIEW_EDITOR = "[contenteditable=true]"
    REVIEW_SUBMIT = 'button:has-text("Add Review")'

    # Read history page: /read_instances/new?book_id={uuid}
    READ_INSTANCES_URL = "https://app.thestorygraph.com/read_instances/new"
    READ_FINISH_DAY = 'select[name="new_read_instance[day]"]'
    READ_FINISH_MONTH = 'select[name="new_read_instance[month]"]'
    READ_FINISH_YEAR = 'select[name="new_read_instance[year]"]'
    READ_START_DAY = 'select[name="new_read_instance[start_day]"]'
    READ_START_MONTH = 'select[name="new_read_instance[start_month]"]'
    READ_START_YEAR = 'select[name="new_read_instance[start_year]"]'
    READ_HISTORY_SUBMIT = 'button:has-text("Save"), input[type="submit"]'

    # Confirmation messages
    BOOK_ON_SHELF_INDICATOR = 'text="Finished", text="Started", text="read"'
