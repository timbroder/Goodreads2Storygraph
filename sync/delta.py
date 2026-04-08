"""Goodreads normalization and delta computation for StoryGraph sync."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Iterable

from .exceptions import GoodreadsExportError
from .library_state import BookRecord, SUPPORTED_STATUSES, normalize_isbn


GOODREADS_STATUS_MAP = {
    "to-read": "to-read",
    "currently-reading": "currently-reading",
    "read": "read",
    "did-not-finish": "did-not-finish",
}


@dataclass(frozen=True)
class DeltaPlan:
    """Books that should be applied to StoryGraph this run."""

    additions: list[BookRecord]
    updates: list[BookRecord]

    @property
    def total_changes(self) -> int:
        return len(self.additions) + len(self.updates)


def _map_goodreads_status(raw_status: str) -> str | None:
    return GOODREADS_STATUS_MAP.get(raw_status.strip().lower())


def load_goodreads_books(csv_path: str) -> dict[str, BookRecord]:
    """Load supported Goodreads shelves from an export CSV."""
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            books: dict[str, BookRecord] = {}

            for row in reader:
                status = _map_goodreads_status(row.get("Exclusive Shelf", ""))
                if status not in SUPPORTED_STATUSES:
                    continue

                title = (row.get("Title") or "").strip()
                author = (row.get("Author") or "").strip()
                if not title or not author:
                    continue

                book = BookRecord(
                    title=title,
                    author=author,
                    status=status,
                    isbn13=normalize_isbn(row.get("ISBN13")) or normalize_isbn(row.get("ISBN")),
                    goodreads_book_id=(row.get("Book Id") or "").strip() or None,
                    source="goodreads",
                )

                # Keep the first matching row for phase 1. Rereads and richer history come later.
                books.setdefault(book.book_key, book)

            return books
    except Exception as exc:
        raise GoodreadsExportError(f"Failed to load Goodreads books: {exc}")


def compute_delta(
    desired_books: dict[str, BookRecord],
    current_books: dict[str, BookRecord],
) -> DeltaPlan:
    """Compare Goodreads desired state with the known StoryGraph baseline."""
    additions: list[BookRecord] = []
    updates: list[BookRecord] = []

    for book_key, desired in desired_books.items():
        current = current_books.get(book_key)
        if current is None:
            additions.append(desired)
            continue

        if current.status != desired.status:
            updates.append(
                BookRecord(
                    title=desired.title,
                    author=desired.author,
                    status=desired.status,
                    isbn13=desired.isbn13,
                    book_key=desired.book_key,
                    goodreads_book_id=desired.goodreads_book_id,
                    storygraph_url=current.storygraph_url,
                    source="goodreads",
                )
            )

    return DeltaPlan(additions=additions, updates=updates)

