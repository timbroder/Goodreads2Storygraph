"""CSV validation and transformation utilities."""

import csv
from pathlib import Path

from .exceptions import GoodreadsExportError
from .state import calculate_csv_hash


def validate_csv(filepath: str) -> bool:
    """
    Validate CSV file integrity and format.

    Args:
        filepath: Path to the CSV file

    Returns:
        True if valid

    Raises:
        GoodreadsExportError: If CSV is invalid
    """
    path = Path(filepath)

    if not path.exists():
        raise GoodreadsExportError(f"CSV file not found: {filepath}")

    if path.stat().st_size == 0:
        raise GoodreadsExportError("CSV file is empty")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Try to read at least one row to validate format
            first_row = next(reader, None)
            if first_row is None:
                raise GoodreadsExportError("CSV has no data rows")

            # Validate expected Goodreads columns are present
            expected_columns = {"Title", "Author", "ISBN"}
            if not any(col in reader.fieldnames for col in expected_columns):
                raise GoodreadsExportError("CSV missing expected Goodreads columns")

        return True
    except csv.Error as e:
        raise GoodreadsExportError(f"Invalid CSV format: {e}")
    except Exception as e:
        raise GoodreadsExportError(f"Failed to validate CSV: {e}")


def calculate_hash(filepath: str) -> str:
    """
    Calculate hash of CSV file (wrapper for state.calculate_csv_hash).

    Args:
        filepath: Path to the CSV file

    Returns:
        SHA256 hash as hex string
    """
    return calculate_csv_hash(filepath)


def count_books(filepath: str) -> int:
    """
    Count the number of books in the CSV file.

    Args:
        filepath: Path to the CSV file

    Returns:
        Number of book entries (rows excluding header)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = sum(1 for _ in reader)
        return count
    except Exception as e:
        raise GoodreadsExportError(f"Failed to count books: {e}")
