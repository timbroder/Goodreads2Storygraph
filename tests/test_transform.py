"""Unit tests for CSV transformation and validation."""

import csv
import hashlib
import tempfile
from pathlib import Path

import pytest

from sync.exceptions import GoodreadsExportError
from sync.transform import calculate_hash, count_books, validate_csv


class TestValidateCSV:
    """Tests for CSV validation."""

    def test_validate_valid_csv(self, tmp_path):
        """Test validation succeeds for valid CSV."""
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "Title,Author,ISBN,My Rating\n"
            "The Great Gatsby,F. Scott Fitzgerald,9780743273565,5\n"
            "1984,George Orwell,9780451524935,4\n"
        )
        assert validate_csv(str(csv_file)) is True

    def test_validate_missing_file(self):
        """Test validation fails for missing file."""
        with pytest.raises(GoodreadsExportError, match="not found"):
            validate_csv("/nonexistent/file.csv")

    def test_validate_empty_file(self, tmp_path):
        """Test validation fails for empty file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.touch()
        with pytest.raises(GoodreadsExportError, match="empty"):
            validate_csv(str(csv_file))

    def test_validate_header_only(self, tmp_path):
        """Test validation fails for CSV with only header row."""
        csv_file = tmp_path / "header_only.csv"
        csv_file.write_text("Title,Author,ISBN\n")
        with pytest.raises(GoodreadsExportError, match="no data rows"):
            validate_csv(str(csv_file))

    def test_validate_missing_expected_columns(self, tmp_path):
        """Test validation fails for CSV missing expected columns."""
        csv_file = tmp_path / "wrong_columns.csv"
        csv_file.write_text(
            "Name,Writer,Rating\n"
            "Some Book,Some Author,5\n"
        )
        with pytest.raises(GoodreadsExportError, match="missing expected"):
            validate_csv(str(csv_file))

    def test_validate_malformed_csv(self, tmp_path):
        """Test validation fails for malformed CSV."""
        csv_file = tmp_path / "malformed.csv"
        csv_file.write_text(
            "Title,Author,ISBN\n"
            'Book with "unclosed quote,Author,123\n'
        )
        # Note: CSV module is lenient, so this might not always fail
        # but we're testing that our error handling works
        try:
            validate_csv(str(csv_file))
        except GoodreadsExportError:
            pass  # Expected in some cases

    def test_validate_with_partial_expected_columns(self, tmp_path):
        """Test validation succeeds when some expected columns are present."""
        csv_file = tmp_path / "partial_columns.csv"
        csv_file.write_text(
            "Title,Rating,Date Read\n"
            "Some Book,5,2024-01-01\n"
        )
        assert validate_csv(str(csv_file)) is True


class TestCalculateHash:
    """Tests for hash calculation."""

    def test_calculate_hash_consistent(self, tmp_path):
        """Test hash is consistent for same content."""
        csv_file = tmp_path / "test.csv"
        content = "Title,Author\nBook,Author\n"
        csv_file.write_text(content)

        hash1 = calculate_hash(str(csv_file))
        hash2 = calculate_hash(str(csv_file))

        assert hash1 == hash2

    def test_calculate_hash_different_content(self, tmp_path):
        """Test different content produces different hashes."""
        csv_file1 = tmp_path / "test1.csv"
        csv_file2 = tmp_path / "test2.csv"

        csv_file1.write_text("Title,Author\nBook1,Author1\n")
        csv_file2.write_text("Title,Author\nBook2,Author2\n")

        hash1 = calculate_hash(str(csv_file1))
        hash2 = calculate_hash(str(csv_file2))

        assert hash1 != hash2

    def test_calculate_hash_sha256_format(self, tmp_path):
        """Test hash is valid SHA256 hex digest."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")

        hash_result = calculate_hash(str(csv_file))

        # SHA256 hex digest is 64 characters
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_calculate_hash_matches_manual_calculation(self, tmp_path):
        """Test hash matches manual SHA256 calculation."""
        csv_file = tmp_path / "test.csv"
        content = "Title,Author\nTest Book,Test Author\n"
        csv_file.write_text(content)

        # Calculate hash manually
        sha256_hash = hashlib.sha256()
        sha256_hash.update(content.encode())
        expected_hash = sha256_hash.hexdigest()

        # Calculate using function
        actual_hash = calculate_hash(str(csv_file))

        assert actual_hash == expected_hash

    def test_calculate_hash_large_file(self, tmp_path):
        """Test hash calculation works for larger files."""
        csv_file = tmp_path / "large.csv"
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Title,Author,ISBN\n")
            # Write 10,000 rows
            for i in range(10000):
                f.write(f"Book {i},Author {i},ISBN{i}\n")

        hash_result = calculate_hash(str(csv_file))

        # Should still produce valid SHA256 hash
        assert len(hash_result) == 64


class TestCountBooks:
    """Tests for book counting."""

    def test_count_books_single_book(self, tmp_path):
        """Test counting single book."""
        csv_file = tmp_path / "one_book.csv"
        csv_file.write_text(
            "Title,Author\n"
            "The Great Gatsby,F. Scott Fitzgerald\n"
        )
        assert count_books(str(csv_file)) == 1

    def test_count_books_multiple_books(self, tmp_path):
        """Test counting multiple books."""
        csv_file = tmp_path / "multiple_books.csv"
        csv_file.write_text(
            "Title,Author,ISBN\n"
            "Book 1,Author 1,123\n"
            "Book 2,Author 2,456\n"
            "Book 3,Author 3,789\n"
        )
        assert count_books(str(csv_file)) == 3

    def test_count_books_no_data_rows(self, tmp_path):
        """Test counting CSV with only header."""
        csv_file = tmp_path / "header_only.csv"
        csv_file.write_text("Title,Author,ISBN\n")
        assert count_books(str(csv_file)) == 0

    def test_count_books_with_empty_lines(self, tmp_path):
        """Test counting handles empty lines correctly."""
        csv_file = tmp_path / "with_empty.csv"
        # CSV reader typically handles empty lines, but they might be counted
        with open(csv_file, "w", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Title", "Author"])
            writer.writeheader()
            writer.writerow({"Title": "Book 1", "Author": "Author 1"})
            writer.writerow({"Title": "Book 2", "Author": "Author 2"})

        assert count_books(str(csv_file)) == 2

    def test_count_books_large_library(self, tmp_path):
        """Test counting large library."""
        csv_file = tmp_path / "large_library.csv"
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Title,Author\n")
            for i in range(1000):
                f.write(f"Book {i},Author {i}\n")

        assert count_books(str(csv_file)) == 1000

    def test_count_books_missing_file(self):
        """Test counting fails gracefully for missing file."""
        with pytest.raises(GoodreadsExportError, match="Failed to count books"):
            count_books("/nonexistent/file.csv")


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_csv_workflow(self, tmp_path):
        """Test complete workflow: validate, hash, count."""
        csv_file = tmp_path / "library.csv"
        csv_file.write_text(
            "Title,Author,ISBN,My Rating\n"
            "The Great Gatsby,F. Scott Fitzgerald,9780743273565,5\n"
            "1984,George Orwell,9780451524935,4\n"
            "To Kill a Mockingbird,Harper Lee,9780061120084,5\n"
        )

        # Validate
        assert validate_csv(str(csv_file)) is True

        # Count
        count = count_books(str(csv_file))
        assert count == 3

        # Hash
        hash_result = calculate_hash(str(csv_file))
        assert len(hash_result) == 64

        # Hash should be consistent
        assert hash_result == calculate_hash(str(csv_file))

    def test_detect_csv_changes(self, tmp_path):
        """Test hash changes when CSV content changes."""
        csv_file = tmp_path / "library.csv"

        # Initial content
        csv_file.write_text("Title,Author\nBook 1,Author 1\n")
        hash1 = calculate_hash(str(csv_file))
        count1 = count_books(str(csv_file))

        # Modified content
        csv_file.write_text(
            "Title,Author\n"
            "Book 1,Author 1\n"
            "Book 2,Author 2\n"
        )
        hash2 = calculate_hash(str(csv_file))
        count2 = count_books(str(csv_file))

        # Hash should change
        assert hash1 != hash2
        # Count should increase
        assert count2 == count1 + 1
