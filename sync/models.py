"""Data models for book records and sync results."""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


def _clean_isbn(raw: str) -> str:
    """Strip Goodreads =\"...\" wrapper and whitespace from ISBN values."""
    if not raw:
        return ""
    # Goodreads wraps ISBNs like ="0743273567"
    cleaned = raw.strip()
    cleaned = cleaned.lstrip("=").strip('"')
    return cleaned


def _safe_int(value: str, default: int = 0) -> int:
    """Convert string to int, returning default on failure."""
    if not value or not value.strip():
        return default
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return default


def _safe_float(value: str, default: float = 0.0) -> float:
    """Convert string to float, returning default on failure."""
    if not value or not value.strip():
        return default
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return default


@dataclass
class BookRecord:
    """A single book from a Goodreads CSV export."""

    book_id: str
    title: str
    author: str
    author_lf: str = ""
    additional_authors: str = ""
    isbn: str = ""
    isbn13: str = ""
    my_rating: int = 0
    average_rating: float = 0.0
    publisher: str = ""
    binding: str = ""
    num_pages: Optional[int] = None
    year_published: Optional[int] = None
    original_pub_year: Optional[int] = None
    date_read: str = ""
    date_added: str = ""
    bookshelves: str = ""
    bookshelves_with_positions: str = ""
    exclusive_shelf: str = ""
    my_review: str = ""
    spoiler: str = ""
    private_notes: str = ""
    read_count: int = 0
    owned_copies: int = 0

    def row_hash(self) -> str:
        """SHA256 of sync-relevant fields for change detection.

        Only hashes fields that matter for StoryGraph sync so that
        changes to non-synced fields (like average_rating) don't
        trigger unnecessary updates.
        """
        parts = [
            self.exclusive_shelf,
            str(self.my_rating),
            self.date_read,
            self.date_added,
            self.my_review,
        ]
        content = "|".join(parts)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def search_isbn(self) -> Optional[str]:
        """Return clean ISBN13 (preferred) or ISBN for StoryGraph search."""
        if self.isbn13:
            return self.isbn13
        if self.isbn:
            return self.isbn
        return None

    def storygraph_shelf(self) -> str:
        """Map Goodreads exclusive_shelf to StoryGraph shelf name."""
        mapping = {
            "read": "read",
            "currently-reading": "currently reading",
            "to-read": "to read",
        }
        return mapping.get(self.exclusive_shelf, "to read")

    @classmethod
    def from_csv_row(cls, row: dict) -> "BookRecord":
        """Create a BookRecord from a Goodreads CSV DictReader row."""
        return cls(
            book_id=row.get("Book Id", "").strip(),
            title=row.get("Title", "").strip(),
            author=row.get("Author", "").strip(),
            author_lf=row.get("Author l-f", "").strip(),
            additional_authors=row.get("Additional Authors", "").strip(),
            isbn=_clean_isbn(row.get("ISBN", "")),
            isbn13=_clean_isbn(row.get("ISBN13", "")),
            my_rating=_safe_int(row.get("My Rating", "0")),
            average_rating=_safe_float(row.get("Average Rating", "0")),
            publisher=row.get("Publisher", "").strip(),
            binding=row.get("Binding", "").strip(),
            num_pages=_safe_int(row.get("Number of Pages", "")) or None,
            year_published=_safe_int(row.get("Year Published", "")) or None,
            original_pub_year=_safe_int(row.get("Original Publication Year", "")) or None,
            date_read=row.get("Date Read", "").strip(),
            date_added=row.get("Date Added", "").strip(),
            bookshelves=row.get("Bookshelves", "").strip(),
            bookshelves_with_positions=row.get("Bookshelves with positions", "").strip(),
            exclusive_shelf=row.get("Exclusive Shelf", "").strip(),
            my_review=row.get("My Review", "").strip(),
            spoiler=row.get("Spoiler", "").strip(),
            private_notes=row.get("Private Notes", "").strip(),
            read_count=_safe_int(row.get("Read Count", "0")),
            owned_copies=_safe_int(row.get("Owned Copies", "0")),
        )


@dataclass
class DeltaResult:
    """Result of comparing current CSV books against stored state."""

    new_books: list = field(default_factory=list)
    changed_books: list = field(default_factory=list)
    removed_book_ids: list = field(default_factory=list)
    unchanged_count: int = 0
    retryable_books: list = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.new_books or self.changed_books or self.retryable_books)

    @property
    def sync_books(self) -> list:
        """All books that need syncing: new + changed + retryable."""
        return self.new_books + self.changed_books + self.retryable_books
