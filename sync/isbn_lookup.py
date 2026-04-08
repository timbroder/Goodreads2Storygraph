"""ISBN lookup using Open Library and Google Books APIs."""

import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

import requests

from .config import get_data_path

logger = logging.getLogger(__name__)

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # seconds between API calls

# Cache file path
_cache: dict = {}
_cache_loaded = False


def _get_cache_path() -> Path:
    """Get path to ISBN cache file."""
    return get_data_path() / "state" / "isbn_cache.json"


def _load_cache() -> dict:
    """Load ISBN cache from disk."""
    global _cache, _cache_loaded
    if _cache_loaded:
        return _cache

    cache_path = _get_cache_path()
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                _cache = json.load(f)
            logger.debug(f"Loaded {len(_cache)} cached ISBNs")
        except Exception as e:
            logger.warning(f"Failed to load ISBN cache: {e}")
            _cache = {}
    else:
        _cache = {}

    _cache_loaded = True
    return _cache


def _save_cache() -> None:
    """Save ISBN cache to disk."""
    cache_path = _get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_path, 'w') as f:
            json.dump(_cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save ISBN cache: {e}")


def _get_cache_key(title: str, author: str) -> str:
    """Generate cache key from title and author."""
    # Normalize for consistent caching
    return f"{title.lower().strip()}|{author.lower().strip()}"


def lookup_isbn(title: str, author: str) -> Optional[str]:
    """
    Look up ISBN for a book using title and author.

    Tries cache first, then Open Library, then Google Books.
    Results are cached locally to avoid repeat API calls.

    Args:
        title: Book title
        author: Author name

    Returns:
        ISBN-13 if found, None otherwise
    """
    # Check cache first
    cache = _load_cache()
    cache_key = _get_cache_key(title, author)

    if cache_key in cache:
        cached_isbn = cache[cache_key]
        # Return cached result without logging (cache hits are silent for cleaner output)
        return cached_isbn

    # Clean up title (remove series info in parentheses)
    clean_title = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()

    # Try Open Library first
    isbn = _lookup_open_library(clean_title, author)
    if isbn:
        logger.debug(f"Found ISBN via Open Library: {isbn}")
        cache[cache_key] = isbn
        _save_cache()
        return isbn

    time.sleep(RATE_LIMIT_DELAY)

    # Fall back to Google Books
    isbn = _lookup_google_books(clean_title, author)
    if isbn:
        logger.debug(f"Found ISBN via Google Books: {isbn}")
        cache[cache_key] = isbn
        _save_cache()
        return isbn

    # Cache the "not found" result too to avoid repeat lookups
    logger.debug(f"No ISBN found for: {title} by {author}")
    cache[cache_key] = None
    _save_cache()
    return None


def _lookup_open_library(title: str, author: str) -> Optional[str]:
    """
    Search Open Library for ISBN.

    Args:
        title: Book title
        author: Author name

    Returns:
        ISBN-13 if found, None otherwise
    """
    try:
        # Search by title and author
        query = f"title:{title} author:{author}"
        url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(query)}&limit=5"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get('docs'):
            for doc in data['docs']:
                # Prefer ISBN-13
                if doc.get('isbn'):
                    for isbn in doc['isbn']:
                        if len(isbn) == 13 and isbn.startswith('978'):
                            return isbn
                    # Fall back to any ISBN-13
                    for isbn in doc['isbn']:
                        if len(isbn) == 13:
                            return isbn
                    # Convert ISBN-10 to ISBN-13
                    for isbn in doc['isbn']:
                        if len(isbn) == 10:
                            return _isbn10_to_isbn13(isbn)

        return None

    except Exception as e:
        logger.debug(f"Open Library lookup failed: {e}")
        return None


def _lookup_google_books(title: str, author: str) -> Optional[str]:
    """
    Search Google Books for ISBN.

    Args:
        title: Book title
        author: Author name

    Returns:
        ISBN-13 if found, None otherwise
    """
    try:
        # Search by title and author
        query = f"intitle:{title}+inauthor:{author}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query)}&maxResults=5"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get('items'):
            for item in data['items']:
                volume_info = item.get('volumeInfo', {})
                identifiers = volume_info.get('industryIdentifiers', [])

                # Prefer ISBN-13
                for identifier in identifiers:
                    if identifier.get('type') == 'ISBN_13':
                        return identifier.get('identifier')

                # Convert ISBN-10 to ISBN-13
                for identifier in identifiers:
                    if identifier.get('type') == 'ISBN_10':
                        isbn10 = identifier.get('identifier')
                        if isbn10:
                            return _isbn10_to_isbn13(isbn10)

        return None

    except Exception as e:
        logger.debug(f"Google Books lookup failed: {e}")
        return None


def _isbn10_to_isbn13(isbn10: str) -> str:
    """
    Convert ISBN-10 to ISBN-13.

    Args:
        isbn10: ISBN-10 string (10 characters)

    Returns:
        ISBN-13 string
    """
    # Remove any hyphens or spaces
    isbn10 = re.sub(r'[-\s]', '', isbn10)

    if len(isbn10) != 10:
        return isbn10

    # ISBN-13 prefix for books
    prefix = "978"

    # Take first 9 digits of ISBN-10
    isbn13_base = prefix + isbn10[:9]

    # Calculate check digit
    total = 0
    for i, digit in enumerate(isbn13_base):
        weight = 1 if i % 2 == 0 else 3
        total += int(digit) * weight

    check_digit = (10 - (total % 10)) % 10

    return isbn13_base + str(check_digit)


def enrich_csv_with_isbns(csv_path: str, output_path: Optional[str] = None) -> Tuple[int, int, int]:
    """
    Read a Goodreads CSV and look up missing ISBNs.

    Args:
        csv_path: Path to the Goodreads export CSV
        output_path: Path to write enriched CSV (defaults to overwriting input)

    Returns:
        Tuple of (books_without_isbn, isbns_found, cache_hits)
    """
    import csv

    if output_path is None:
        output_path = csv_path

    # Load cache to check for hits
    cache = _load_cache()

    # Read the CSV
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    books_without_isbn = 0
    isbns_found = 0
    cache_hits = 0
    api_lookups = 0

    for row in rows:
        # Check if ISBN is missing
        isbn = row.get('ISBN', '').strip()
        isbn13 = row.get('ISBN13', '').strip()

        # Clean up Goodreads ISBN format (="..." or empty)
        isbn_clean = isbn.replace('="', '').replace('"', '').strip()
        isbn13_clean = isbn13.replace('="', '').replace('"', '').strip()

        if not isbn_clean and not isbn13_clean:
            books_without_isbn += 1
            title = row.get('Title', '')
            author = row.get('Author', '')

            # Check if this is a cache hit
            cache_key = _get_cache_key(title, author)
            is_cached = cache_key in cache

            if is_cached:
                cache_hits += 1
            else:
                api_lookups += 1
                logger.info(f"Looking up ISBN for: {title[:50]}...")

            found_isbn = lookup_isbn(title, author)

            if found_isbn:
                isbns_found += 1
                # Update the row with the found ISBN
                row['ISBN13'] = f'="{found_isbn}"'
                if not is_cached:
                    logger.info(f"  Found ISBN: {found_isbn}")
            else:
                if not is_cached:
                    logger.warning(f"  No ISBN found for: {title}")

            # Only rate limit for API calls, not cache hits
            if not is_cached:
                time.sleep(RATE_LIMIT_DELAY)

    # Write the enriched CSV
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"ISBN enrichment: {cache_hits} from cache, {api_lookups} API lookups")
    return books_without_isbn, isbns_found, cache_hits
