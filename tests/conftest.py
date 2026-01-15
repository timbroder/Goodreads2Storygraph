"""Shared pytest fixtures and configuration."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(tmp_path_factory):
    """Create a temporary directory for test files."""
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "Title,Author,ISBN,My Rating,Date Read\n"
        "The Great Gatsby,F. Scott Fitzgerald,9780743273565,5,2024-01-01\n"
        "1984,George Orwell,9780451524935,4,2024-01-15\n"
        "To Kill a Mockingbird,Harper Lee,9780061120084,5,2024-02-01\n"
    )
    return csv_file
