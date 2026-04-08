"""Tests for BookRecord data model."""

import pytest

from sync.models import BookRecord, DeltaResult, _clean_isbn, _safe_int, _safe_float


class TestCleanISBN:
    def test_strips_goodreads_wrapper(self):
        assert _clean_isbn('="0743273567"') == "0743273567"

    def test_strips_partial_wrapper(self):
        assert _clean_isbn('"0743273567"') == "0743273567"

    def test_plain_isbn_unchanged(self):
        assert _clean_isbn("9780743273565") == "9780743273565"

    def test_empty_string(self):
        assert _clean_isbn("") == ""

    def test_whitespace(self):
        assert _clean_isbn("  9780743273565  ") == "9780743273565"

    def test_none_returns_empty(self):
        assert _clean_isbn(None) == ""


class TestSafeInt:
    def test_valid_int(self):
        assert _safe_int("42") == 42

    def test_empty_string(self):
        assert _safe_int("") == 0

    def test_none(self):
        assert _safe_int(None) == 0

    def test_invalid(self):
        assert _safe_int("abc") == 0

    def test_with_whitespace(self):
        assert _safe_int("  5  ") == 5

    def test_custom_default(self):
        assert _safe_int("", default=-1) == -1


class TestSafeFloat:
    def test_valid_float(self):
        assert _safe_float("3.14") == 3.14

    def test_valid_int_string(self):
        assert _safe_float("5") == 5.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0


class TestBookRecord:
    def _make_book(self, **overrides):
        defaults = {
            "book_id": "12345",
            "title": "The Great Gatsby",
            "author": "F. Scott Fitzgerald",
            "exclusive_shelf": "read",
            "my_rating": 5,
            "date_read": "2024/01/15",
            "date_added": "2024/01/01",
            "my_review": "A classic.",
            "isbn": "0743273567",
            "isbn13": "9780743273565",
        }
        defaults.update(overrides)
        return BookRecord(**defaults)

    def test_row_hash_consistent(self):
        book1 = self._make_book()
        book2 = self._make_book()
        assert book1.row_hash() == book2.row_hash()

    def test_row_hash_changes_on_shelf_change(self):
        book1 = self._make_book(exclusive_shelf="read")
        book2 = self._make_book(exclusive_shelf="to-read")
        assert book1.row_hash() != book2.row_hash()

    def test_row_hash_changes_on_rating_change(self):
        book1 = self._make_book(my_rating=5)
        book2 = self._make_book(my_rating=4)
        assert book1.row_hash() != book2.row_hash()

    def test_row_hash_changes_on_review_change(self):
        book1 = self._make_book(my_review="A classic.")
        book2 = self._make_book(my_review="Updated review.")
        assert book1.row_hash() != book2.row_hash()

    def test_row_hash_ignores_average_rating(self):
        book1 = self._make_book(average_rating=3.5)
        book2 = self._make_book(average_rating=4.2)
        assert book1.row_hash() == book2.row_hash()

    def test_row_hash_ignores_publisher(self):
        book1 = self._make_book(publisher="Penguin")
        book2 = self._make_book(publisher="Random House")
        assert book1.row_hash() == book2.row_hash()

    def test_search_isbn_prefers_isbn13(self):
        book = self._make_book(isbn="0743273567", isbn13="9780743273565")
        assert book.search_isbn() == "9780743273565"

    def test_search_isbn_falls_back_to_isbn(self):
        book = self._make_book(isbn="0743273567", isbn13="")
        assert book.search_isbn() == "0743273567"

    def test_search_isbn_returns_none_when_empty(self):
        book = self._make_book(isbn="", isbn13="")
        assert book.search_isbn() is None

    def test_storygraph_shelf_read(self):
        book = self._make_book(exclusive_shelf="read")
        assert book.storygraph_shelf() == "read"

    def test_storygraph_shelf_currently_reading(self):
        book = self._make_book(exclusive_shelf="currently-reading")
        assert book.storygraph_shelf() == "currently reading"

    def test_storygraph_shelf_to_read(self):
        book = self._make_book(exclusive_shelf="to-read")
        assert book.storygraph_shelf() == "to read"

    def test_storygraph_shelf_unknown_defaults_to_read(self):
        book = self._make_book(exclusive_shelf="custom-shelf")
        assert book.storygraph_shelf() == "to read"


class TestBookRecordFromCSVRow:
    def test_parses_full_row(self):
        row = {
            "Book Id": "12345",
            "Title": "The Great Gatsby",
            "Author": "F. Scott Fitzgerald",
            "Author l-f": "Fitzgerald, F. Scott",
            "Additional Authors": "",
            "ISBN": '="0743273567"',
            "ISBN13": '="9780743273565"',
            "My Rating": "5",
            "Average Rating": "3.91",
            "Publisher": "Scribner",
            "Binding": "Paperback",
            "Number of Pages": "184",
            "Year Published": "2004",
            "Original Publication Year": "1925",
            "Date Read": "2024/01/15",
            "Date Added": "2024/01/01",
            "Bookshelves": "favorites, classics",
            "Bookshelves with positions": "favorites (#1), classics (#3)",
            "Exclusive Shelf": "read",
            "My Review": "A classic.",
            "Spoiler": "",
            "Private Notes": "",
            "Read Count": "2",
            "Owned Copies": "1",
        }
        book = BookRecord.from_csv_row(row)
        assert book.book_id == "12345"
        assert book.title == "The Great Gatsby"
        assert book.isbn == "0743273567"
        assert book.isbn13 == "9780743273565"
        assert book.my_rating == 5
        assert book.average_rating == 3.91
        assert book.num_pages == 184
        assert book.year_published == 2004
        assert book.original_pub_year == 1925
        assert book.exclusive_shelf == "read"
        assert book.read_count == 2
        assert book.owned_copies == 1

    def test_handles_missing_fields(self):
        row = {"Book Id": "99", "Title": "Minimal Book", "Author": "Someone"}
        book = BookRecord.from_csv_row(row)
        assert book.book_id == "99"
        assert book.isbn == ""
        assert book.my_rating == 0
        assert book.num_pages is None

    def test_handles_empty_numeric_fields(self):
        row = {
            "Book Id": "99",
            "Title": "Test",
            "Author": "Author",
            "My Rating": "",
            "Number of Pages": "",
            "Read Count": "",
        }
        book = BookRecord.from_csv_row(row)
        assert book.my_rating == 0
        assert book.num_pages is None
        assert book.read_count == 0


class TestDeltaResult:
    def test_has_changes_with_new_books(self):
        delta = DeltaResult(new_books=["book1"])
        assert delta.has_changes is True

    def test_has_changes_with_changed_books(self):
        delta = DeltaResult(changed_books=["book1"])
        assert delta.has_changes is True

    def test_no_changes_when_empty(self):
        delta = DeltaResult()
        assert delta.has_changes is False

    def test_no_changes_with_only_removals(self):
        delta = DeltaResult(removed_book_ids=["123"])
        assert delta.has_changes is False

    def test_sync_books_combines_lists(self):
        delta = DeltaResult(
            new_books=["a"],
            changed_books=["b"],
            retryable_books=["c"],
        )
        assert delta.sync_books == ["a", "b", "c"]
