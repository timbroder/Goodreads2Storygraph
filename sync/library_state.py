"""Local library state database and shared book normalization helpers."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .config import get_data_path


SUPPORTED_STATUSES = {
    "to-read",
    "currently-reading",
    "read",
    "did-not-finish",
}


def get_library_db_path() -> Path:
    """Return the default SQLite path for local library state."""
    return get_data_path() / "state" / "library_state.sqlite3"


def normalize_text(value: str) -> str:
    """Normalize text for resilient cross-site matching."""
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return re.sub(r"[^a-z0-9 ]", "", normalized)


def normalize_isbn(value: Optional[str]) -> Optional[str]:
    """Normalize ISBN values exported from Goodreads or scraped from StoryGraph."""
    if not value:
        return None

    cleaned = value.strip()
    cleaned = cleaned.removeprefix('="').removesuffix('"')
    cleaned = cleaned.replace("-", "").replace(" ", "")
    cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch.upper() == "X")
    return cleaned or None


def make_book_key(title: str, author: str, isbn13: Optional[str] = None) -> str:
    """Create a stable lookup key shared between Goodreads and StoryGraph."""
    normalized_isbn = normalize_isbn(isbn13)
    if normalized_isbn:
        return f"isbn:{normalized_isbn}"
    return f"text:{normalize_text(title)}|{normalize_text(author)}"


@dataclass(frozen=True)
class BookRecord:
    """Normalized representation of a library book."""

    title: str
    author: str
    status: str
    isbn13: Optional[str] = None
    book_key: Optional[str] = None
    goodreads_book_id: Optional[str] = None
    storygraph_url: Optional[str] = None
    source: str = "unknown"

    def __post_init__(self) -> None:
        if self.status not in SUPPORTED_STATUSES:
            raise ValueError(f"Unsupported status: {self.status}")

        normalized_isbn = normalize_isbn(self.isbn13)
        resolved_key = self.book_key or make_book_key(self.title, self.author, normalized_isbn)

        object.__setattr__(self, "isbn13", normalized_isbn)
        object.__setattr__(self, "book_key", resolved_key)


class LibraryDatabase:
    """Simple SQLite wrapper around local StoryGraph state."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else get_library_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    account_name TEXT NOT NULL,
                    book_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    isbn13 TEXT,
                    goodreads_book_id TEXT,
                    storygraph_url TEXT,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_name, book_key)
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    account_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_name, key)
                );

                CREATE INDEX IF NOT EXISTS idx_books_account_status
                    ON books(account_name, status);
                """
            )

    def get_books(self, account_name: str) -> dict[str, BookRecord]:
        """Return the current known StoryGraph state for an account."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT title, author, status, isbn13, book_key, goodreads_book_id, storygraph_url, source
                FROM books
                WHERE account_name = ?
                """,
                (account_name,),
            ).fetchall()

        return {
            row["book_key"]: BookRecord(
                title=row["title"],
                author=row["author"],
                status=row["status"],
                isbn13=row["isbn13"],
                book_key=row["book_key"],
                goodreads_book_id=row["goodreads_book_id"],
                storygraph_url=row["storygraph_url"],
                source=row["source"],
            )
            for row in rows
        }

    def replace_books(self, account_name: str, books: Iterable[BookRecord], source: str) -> int:
        """Replace the full known library state for an account."""
        timestamp = datetime.now(timezone.utc).isoformat()
        materialized_books = [
            BookRecord(
                title=book.title,
                author=book.author,
                status=book.status,
                isbn13=book.isbn13,
                book_key=book.book_key,
                goodreads_book_id=book.goodreads_book_id,
                storygraph_url=book.storygraph_url,
                source=source,
            )
            for book in books
        ]

        with self._connect() as conn:
            conn.execute("DELETE FROM books WHERE account_name = ?", (account_name,))
            conn.executemany(
                """
                INSERT INTO books (
                    account_name, book_key, title, author, isbn13, goodreads_book_id,
                    storygraph_url, status, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        account_name,
                        book.book_key,
                        book.title,
                        book.author,
                        book.isbn13,
                        book.goodreads_book_id,
                        book.storygraph_url,
                        book.status,
                        book.source,
                        timestamp,
                    )
                    for book in materialized_books
                ],
            )

        return len(materialized_books)

    def upsert_book(self, account_name: str, book: BookRecord) -> None:
        """Insert or update a single known StoryGraph book."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO books (
                    account_name, book_key, title, author, isbn13, goodreads_book_id,
                    storygraph_url, status, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_name, book_key) DO UPDATE SET
                    title = excluded.title,
                    author = excluded.author,
                    isbn13 = excluded.isbn13,
                    goodreads_book_id = excluded.goodreads_book_id,
                    storygraph_url = excluded.storygraph_url,
                    status = excluded.status,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    account_name,
                    book.book_key,
                    book.title,
                    book.author,
                    book.isbn13,
                    book.goodreads_book_id,
                    book.storygraph_url,
                    book.status,
                    book.source,
                    timestamp,
                ),
            )

    def get_metadata(self, account_name: str, key: str) -> Optional[str]:
        """Return a metadata value for an account."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE account_name = ? AND key = ?",
                (account_name, key),
            ).fetchone()
        return row["value"] if row else None

    def set_metadata(self, account_name: str, key: str, value: str) -> None:
        """Store account-scoped metadata."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO metadata(account_name, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_name, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (account_name, key, value, timestamp),
            )
