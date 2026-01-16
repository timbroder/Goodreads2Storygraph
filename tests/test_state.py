"""Unit tests for state management and persistence."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sync.exceptions import StateError
from sync.state import (
    calculate_csv_hash,
    get_state_file,
    load_state,
    save_state,
    should_skip_upload,
)


class TestCalculateCSVHash:
    """Tests for CSV hash calculation."""

    def test_calculate_hash_valid_file(self, tmp_path):
        """Test hash calculation for valid file."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title,Author\nBook,Author\n")

        hash_result = calculate_csv_hash(str(csv_file))

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA256 hex digest

    def test_calculate_hash_consistency(self, tmp_path):
        """Test hash is consistent for same file content."""
        csv_file = tmp_path / "test.csv"
        content = "Title,Author\nTest Book,Test Author\n"
        csv_file.write_text(content)

        hash1 = calculate_csv_hash(str(csv_file))
        hash2 = calculate_csv_hash(str(csv_file))

        assert hash1 == hash2

    def test_calculate_hash_different_content(self, tmp_path):
        """Test different content produces different hashes."""
        file1 = tmp_path / "test1.csv"
        file2 = tmp_path / "test2.csv"

        file1.write_text("Title\nBook 1\n")
        file2.write_text("Title\nBook 2\n")

        hash1 = calculate_csv_hash(str(file1))
        hash2 = calculate_csv_hash(str(file2))

        assert hash1 != hash2

    def test_calculate_hash_format(self, tmp_path):
        """Test hash is valid SHA256 format."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nContent\n")

        hash_result = calculate_csv_hash(str(csv_file))

        # SHA256 hex digest should only contain 0-9 and a-f
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_calculate_hash_matches_manual_calculation(self, tmp_path):
        """Test hash matches manual SHA256 calculation."""
        import hashlib

        csv_file = tmp_path / "test.csv"
        content = "Title,Author\nTest,Test\n"
        csv_file.write_text(content)

        # Manual calculation
        sha256_hash = hashlib.sha256()
        sha256_hash.update(content.encode())
        expected_hash = sha256_hash.hexdigest()

        # Function calculation
        result_hash = calculate_csv_hash(str(csv_file))

        assert result_hash == expected_hash

    def test_calculate_hash_large_file(self, tmp_path):
        """Test hash calculation for large file."""
        csv_file = tmp_path / "large.csv"

        # Create a CSV with 1000 lines
        with open(csv_file, "w") as f:
            f.write("Title,Author\n")
            for i in range(1000):
                f.write(f"Book {i},Author {i}\n")

        hash_result = calculate_csv_hash(str(csv_file))

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64

    def test_calculate_hash_missing_file(self):
        """Test error for missing file."""
        with pytest.raises(StateError, match="Failed to calculate hash"):
            calculate_csv_hash("/nonexistent/file.csv")


class TestLoadState:
    """Tests for state loading."""

    def test_load_state_missing_file(self, tmp_path):
        """Test loading when state file doesn't exist."""
        with patch("sync.state.get_state_file", return_value=tmp_path / "nonexistent.json"):
            result = load_state("test_account")
            assert result is None

    def test_load_state_valid(self, tmp_path):
        """Test loading valid state file."""
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": "abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 42,
            "account_name": "test_account"
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            result = load_state("test_account")

        assert result == state_data
        assert result["last_hash"] == "abc123"
        assert result["last_book_count"] == 42

    def test_load_state_missing_required_keys(self, tmp_path):
        """Test error when state file is missing required keys."""
        state_file = tmp_path / "state.json"
        state_data = {"last_hash": "abc123"}  # Missing other required keys
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            with pytest.raises(StateError, match="missing required keys"):
                load_state("test_account")

    def test_load_state_corrupted_json(self, tmp_path):
        """Test error handling for corrupted JSON."""
        state_file = tmp_path / "state.json"
        state_file.write_text("{invalid json")

        with patch("sync.state.get_state_file", return_value=state_file):
            with pytest.raises(StateError, match="corrupted"):
                load_state("test_account")

    def test_load_state_all_required_keys_present(self, tmp_path):
        """Test validation succeeds when all required keys present."""
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": "def456",
            "last_sync_timestamp": "2024-01-15T12:00:00",
            "last_book_count": 100,
            "extra_field": "ignored"  # Extra fields should be OK
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            result = load_state("test_account")

        assert result["last_hash"] == "def456"
        assert result["last_book_count"] == 100


class TestSaveState:
    """Tests for state saving."""

    def test_save_state_creates_directory(self, tmp_path):
        """Test save creates parent directories if they don't exist."""
        state_dir = tmp_path / "nested" / "dir"
        state_file = state_dir / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="abc123", book_count=10, account_name="test_account")

        assert state_file.exists()
        assert state_dir.exists()

    def test_save_state_valid_content(self, tmp_path):
        """Test saved state contains correct data."""
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="xyz789", book_count=25, account_name="test_account")

        assert state_file.exists()

        with open(state_file) as f:
            data = json.load(f)

        assert data["last_hash"] == "xyz789"
        assert data["last_book_count"] == 25
        assert data["account_name"] == "test_account"
        assert "last_sync_timestamp" in data

        # Verify timestamp format
        datetime.fromisoformat(data["last_sync_timestamp"])

    def test_save_state_overwrites_existing(self, tmp_path):
        """Test saving overwrites existing state file."""
        state_file = tmp_path / "state.json"

        # Create initial state
        initial_data = {
            "last_hash": "old_hash",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 5
        }
        state_file.write_text(json.dumps(initial_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="new_hash", book_count=20, account_name="test_account")

        with open(state_file) as f:
            data = json.load(f)

        assert data["last_hash"] == "new_hash"
        assert data["last_book_count"] == 20

    def test_save_state_timestamp_format(self, tmp_path):
        """Test timestamp is in ISO format."""
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            before = datetime.utcnow()
            save_state(csv_hash="hash123", book_count=5, account_name="test_account")
            after = datetime.utcnow()

        with open(state_file) as f:
            data = json.load(f)

        # Parse timestamp
        saved_time = datetime.fromisoformat(data["last_sync_timestamp"])

        # Verify timestamp is between before and after
        assert before <= saved_time <= after


class TestShouldSkipUpload:
    """Tests for skip upload logic."""

    def test_should_skip_with_force_sync(self, tmp_path):
        """Test force sync always uploads."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")

        should_skip, reason = should_skip_upload(str(csv_file), "test_account", force_sync=True)

        assert should_skip is False
        assert "Force sync" in reason

    def test_should_skip_no_previous_state(self, tmp_path):
        """Test upload when no previous state exists."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")

        state_file = tmp_path / "nonexistent.json"
        with patch("sync.state.get_state_file", return_value=state_file):
            should_skip, reason = should_skip_upload(str(csv_file), "test_account")

        assert should_skip is False
        assert "No previous state" in reason

    def test_should_skip_csv_unchanged(self, tmp_path):
        """Test skip when CSV hasn't changed."""
        csv_file = tmp_path / "test.csv"
        csv_content = "Title,Author\nBook 1,Author 1\n"
        csv_file.write_text(csv_content)

        # Calculate hash
        csv_hash = calculate_csv_hash(str(csv_file))

        # Create state with same hash
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": csv_hash,
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            should_skip, reason = should_skip_upload(str(csv_file), "test_account")

        assert should_skip is True
        assert "unchanged" in reason

    def test_should_skip_csv_changed(self, tmp_path):
        """Test upload when CSV has changed."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook 1\n")

        # Create state with different hash
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": "different_hash",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            should_skip, reason = should_skip_upload(str(csv_file), "test_account")

        assert should_skip is False
        assert "changed" in reason

    def test_should_skip_force_overrides_unchanged(self, tmp_path):
        """Test force sync overrides unchanged detection."""
        csv_file = tmp_path / "test.csv"
        csv_content = "Title\nBook\n"
        csv_file.write_text(csv_content)

        csv_hash = calculate_csv_hash(str(csv_file))

        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": csv_hash,  # Same hash
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.get_state_file", return_value=state_file):
            # Without force: should skip
            should_skip1, _ = should_skip_upload(str(csv_file), "test_account", force_sync=False)
            # With force: should not skip
            should_skip2, _ = should_skip_upload(str(csv_file), "test_account", force_sync=True)

        assert should_skip1 is True
        assert should_skip2 is False


class TestIntegration:
    """Integration tests for state management workflow."""

    def test_full_state_workflow(self, tmp_path):
        """Test complete workflow: save, load, check."""
        csv_file = tmp_path / "library.csv"
        csv_content = "Title,Author\nBook 1,Author 1\n"
        csv_file.write_text(csv_content)

        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            # Calculate hash and save state
            csv_hash = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=csv_hash, book_count=1, account_name="test_account")

            # Load state back
            loaded_state = load_state("test_account")

            assert loaded_state is not None
            assert loaded_state["last_hash"] == csv_hash
            assert loaded_state["last_book_count"] == 1

            # Check if upload should be skipped (it should, since CSV unchanged)
            should_skip, reason = should_skip_upload(str(csv_file), "test_account")

            assert should_skip is True

    def test_detect_library_change(self, tmp_path):
        """Test detection of library changes."""
        csv_file = tmp_path / "library.csv"
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            # Initial CSV and state
            csv_file.write_text("Title\nBook 1\n")
            hash1 = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=hash1, book_count=1, account_name="test_account")

            # Verify upload would be skipped
            should_skip1, _ = should_skip_upload(str(csv_file), "test_account")
            assert should_skip1 is True

            # Modify CSV
            csv_file.write_text("Title\nBook 1\nBook 2\n")
            hash2 = calculate_csv_hash(str(csv_file))

            # Verify hashes are different
            assert hash1 != hash2

            # Verify upload would NOT be skipped
            should_skip2, reason = should_skip_upload(str(csv_file), "test_account")
            assert should_skip2 is False
            assert "changed" in reason

            # Save new state
            save_state(csv_hash=hash2, book_count=2, account_name="test_account")

            # Verify upload would now be skipped
            should_skip3, _ = should_skip_upload(str(csv_file), "test_account")
            assert should_skip3 is True

    def test_state_persistence_across_runs(self, tmp_path):
        """Test state persists correctly across multiple runs."""
        csv_file = tmp_path / "library.csv"
        csv_file.write_text("Title\nBook\n")
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            # First run: save state
            hash1 = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=hash1, book_count=1, account_name="test_account")

            # Simulate new run: load state
            state = load_state("test_account")
            assert state["last_hash"] == hash1

            # Check skip logic
            should_skip, _ = should_skip_upload(str(csv_file), "test_account")
            assert should_skip is True
