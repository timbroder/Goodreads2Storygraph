"""Tests for Goodreads delta planning."""

from sync.delta import compute_delta, load_goodreads_books
from sync.library_state import BookRecord


class TestLoadGoodreadsBooks:
    """Goodreads CSV normalization rules."""

    def test_load_supported_shelves(self, tmp_path):
        """Only StoryGraph-compatible exclusive shelves should be loaded."""
        csv_file = tmp_path / "goodreads.csv"
        csv_file.write_text(
            "Book Id,Title,Author,ISBN,ISBN13,Exclusive Shelf\n"
            '1,Neuromancer,William Gibson,="",="9780441569564",to-read\n'
            '2,The Hobbit,J.R.R. Tolkien,="",="",currently-reading\n'
            '3,Reference Book,Someone,="",="",favorites\n'
        )

        books = load_goodreads_books(str(csv_file))

        assert len(books) == 2
        assert books["isbn:9780441569564"].status == "to-read"
        assert books["text:the hobbit|jrr tolkien"].status == "currently-reading"

    def test_dedupes_multiple_rows_for_same_book(self, tmp_path):
        """Repeated Goodreads rows should collapse to a single phase 1 record."""
        csv_file = tmp_path / "goodreads.csv"
        csv_file.write_text(
            "Book Id,Title,Author,ISBN,ISBN13,Exclusive Shelf\n"
            '1,Neuromancer,William Gibson,="",="9780441569564",read\n'
            '1,Neuromancer,William Gibson,="",="9780441569564",read\n'
        )

        books = load_goodreads_books(str(csv_file))
        assert len(books) == 1


class TestComputeDelta:
    """Diff rules between Goodreads desired state and StoryGraph baseline."""

    def test_detects_additions_and_updates(self):
        """Missing books are additions and status changes are updates."""
        desired = {
            "isbn:9780441569564": BookRecord("Neuromancer", "William Gibson", "read", isbn13="9780441569564"),
            "text:snow crash|neal stephenson": BookRecord("Snow Crash", "Neal Stephenson", "to-read"),
        }
        current = {
            "isbn:9780441569564": BookRecord(
                "Neuromancer",
                "William Gibson",
                "to-read",
                isbn13="9780441569564",
                storygraph_url="https://app.thestorygraph.com/books/neuromancer",
                source="storygraph_seed",
            ),
        }

        plan = compute_delta(desired, current)

        assert len(plan.additions) == 1
        assert len(plan.updates) == 1
        assert plan.additions[0].title == "Snow Crash"
        assert plan.updates[0].storygraph_url == "https://app.thestorygraph.com/books/neuromancer"

    def test_ignores_unchanged_books(self):
        """Already-matching records should not create work."""
        desired = {
            "isbn:9780441569564": BookRecord("Neuromancer", "William Gibson", "read", isbn13="9780441569564"),
        }
        current = {
            "isbn:9780441569564": BookRecord("Neuromancer", "William Gibson", "read", isbn13="9780441569564"),
        }

        plan = compute_delta(desired, current)

        assert plan.total_changes == 0
