"""Tests for local library state and normalization helpers."""

from sync.library_state import BookRecord, LibraryDatabase, make_book_key, normalize_isbn, normalize_text


class TestNormalization:
    """Normalization helpers used across Goodreads and StoryGraph."""

    def test_normalize_isbn_goodreads_wrapped_value(self):
        """Goodreads wraps ISBN13 values like =\"978...\" in CSV exports."""
        assert normalize_isbn('="9781781100523"') == "9781781100523"

    def test_normalize_isbn_removes_punctuation(self):
        """ISBN cleanup should remove separators."""
        assert normalize_isbn("978-1-4028-9462-6") == "9781402894626"

    def test_make_book_key_prefers_isbn(self):
        """ISBN-backed keys should be preferred when available."""
        assert make_book_key("Neuromancer", "William Gibson", "9780441569564") == "isbn:9780441569564"

    def test_make_book_key_falls_back_to_title_author(self):
        """Text fallback keys should normalize spacing and punctuation."""
        assert make_book_key("Good Material", "Dolly Alderton", None) == "text:good material|dolly alderton"

    def test_normalize_text_collapses_spacing(self):
        """Title and author matching should tolerate repeated spaces."""
        assert normalize_text("  The   Hobbit  ") == "the hobbit"


class TestLibraryDatabase:
    """SQLite-backed local state behavior."""

    def test_replace_and_load_books(self, tmp_path):
        """Replacing the baseline should persist all provided books."""
        db = LibraryDatabase(tmp_path / "library.sqlite3")
        count = db.replace_books(
            "default",
            [
                BookRecord("Neuromancer", "William Gibson", "to-read", isbn13="9780441569564"),
                BookRecord("Snow Crash", "Neal Stephenson", "read"),
            ],
            source="storygraph_seed",
        )

        books = db.get_books("default")

        assert count == 2
        assert len(books) == 2
        assert books["isbn:9780441569564"].status == "to-read"
        assert books["text:snow crash|neal stephenson"].source == "storygraph_seed"

    def test_upsert_book_updates_existing_row(self, tmp_path):
        """Upserting a book should overwrite changed status and URL."""
        db = LibraryDatabase(tmp_path / "library.sqlite3")
        original = BookRecord("Neuromancer", "William Gibson", "to-read", isbn13="9780441569564")
        updated = BookRecord(
            "Neuromancer",
            "William Gibson",
            "read",
            isbn13="9780441569564",
            storygraph_url="https://app.thestorygraph.com/books/neuromancer",
            source="storygraph_sync",
        )

        db.replace_books("default", [original], source="storygraph_seed")
        db.upsert_book("default", updated)

        loaded = db.get_books("default")["isbn:9780441569564"]
        assert loaded.status == "read"
        assert loaded.storygraph_url == "https://app.thestorygraph.com/books/neuromancer"
        assert loaded.source == "storygraph_sync"

    def test_metadata_round_trip(self, tmp_path):
        """Metadata should store per-account sync values."""
        db = LibraryDatabase(tmp_path / "library.sqlite3")
        db.set_metadata("default", "last_goodreads_hash", "abc123")

        assert db.get_metadata("default", "last_goodreads_hash") == "abc123"
        assert db.get_metadata("default", "missing") is None

