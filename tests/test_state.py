"""Unit tests for state management and persistence."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sync.exceptions import StateError
from sync.state import (
    STATE_FILE,
    calculate_csv_hash,
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

    def test_calculate_hash_missing_file(self):
        """Test error handling for missing file."""
        with pytest.raises(StateError, match="Failed to calculate hash"):
            calculate_csv_hash("/nonexistent/file.csv")

    def test_calculate_hash_large_file(self, tmp_path):
        """Test hash calculation for large files (tests chunked reading)."""
        csv_file = tmp_path / "large.csv"
        # Create file larger than 4096 bytes (chunk size)
        with open(csv_file, "w") as f:
            f.write("Title,Author\n")
            for i in range(1000):
                f.write(f"Book {i},Author {i}\n")

        hash_result = calculate_csv_hash(str(csv_file))

        assert len(hash_result) == 64


class TestLoadState:
    """Tests for state loading."""

    def test_load_state_missing_file(self, tmp_path):
        """Test loading when state file doesn't exist."""
        with patch("sync.state.STATE_FILE", tmp_path / "nonexistent.json"):
            result = load_state()
            assert result is None

    def test_load_state_valid(self, tmp_path):
        """Test loading valid state file."""
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": "abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 42
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.STATE_FILE", state_file):
            result = load_state()

        assert result == state_data
        assert result["last_hash"] == "abc123"
        assert result["last_book_count"] == 42

    def test_load_state_missing_required_keys(self, tmp_path):
        """Test error when state file is missing required keys."""
        state_file = tmp_path / "state.json"
        state_data = {"last_hash": "abc123"}  # Missing other required keys
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.STATE_FILE", state_file):
            with pytest.raises(StateError, match="missing required keys"):
                load_state()

    def test_load_state_corrupted_json(self, tmp_path):
        """Test error handling for corrupted JSON."""
        state_file = tmp_path / "state.json"
        state_file.write_text("{invalid json")

        with patch("sync.state.STATE_FILE", state_file):
            with pytest.raises(StateError, match="corrupted"):
                load_state()

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

        with patch("sync.state.STATE_FILE", state_file):
            result = load_state()

        assert result["last_hash"] == "def456"
        assert result["last_book_count"] == 100


class TestSaveState:
    """Tests for state saving."""

    def test_save_state_creates_directory(self, tmp_path):
        """Test save creates parent directories if they don't exist."""
        state_file = tmp_path / "new_dir" / "state.json"

        with patch("sync.state.STATE_FILE", state_file):
            save_state(csv_hash="abc123", book_count=10)

        assert state_file.exists()
        assert state_file.parent.exists()

    def test_save_state_valid_content(self, tmp_path):
        """Test save writes correct state structure."""
        state_file = tmp_path / "state.json"

        with patch("sync.state.STATE_FILE", state_file):
            save_state(csv_hash="xyz789", book_count=25)

        # Read and verify content
        with open(state_file) as f:
            state = json.load(f)

        assert state["last_hash"] == "xyz789"
        assert state["last_book_count"] == 25
        assert "last_sync_timestamp" in state

        # Verify timestamp is valid ISO format
        datetime.fromisoformat(state["last_sync_timestamp"])

    def test_save_state_overwrites_existing(self, tmp_path):
        """Test save overwrites existing state file."""
        state_file = tmp_path / "state.json"
        old_state = {
            "last_hash": "old_hash",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 10
        }
        state_file.write_text(json.dumps(old_state))

        with patch("sync.state.STATE_FILE", state_file):
            save_state(csv_hash="new_hash", book_count=20)

        # Read and verify new content
        with open(state_file) as f:
            state = json.load(f)

        assert state["last_hash"] == "new_hash"
        assert state["last_book_count"] == 20
        assert state["last_hash"] != "old_hash"

    def test_save_state_timestamp_format(self, tmp_path):
        """Test timestamp is in ISO format."""
        state_file = tmp_path / "state.json"

        with patch("sync.state.STATE_FILE", state_file):
            before_save = datetime.utcnow()
            save_state(csv_hash="hash123", book_count=5)
            after_save = datetime.utcnow()

        with open(state_file) as f:
            state = json.load(f)

        # Parse timestamp
        timestamp = datetime.fromisoformat(state["last_sync_timestamp"])

        # Should be between before and after
        assert before_save <= timestamp <= after_save


class TestShouldSkipUpload:
    """Tests for upload skip logic."""

    def test_should_skip_force_sync(self, tmp_path):
        """Test force sync always returns False (never skip)."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")

        should_skip, reason = should_skip_upload(str(csv_file), force_sync=True)

        assert should_skip is False
        assert "Force sync" in reason

    def test_should_skip_no_previous_state(self, tmp_path):
        """Test returns False when no previous state exists."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        state_file = tmp_path / "state.json"

        with patch("sync.state.STATE_FILE", state_file):
            should_skip, reason = should_skip_upload(str(csv_file))

        assert should_skip is False
        assert "No previous state" in reason

    def test_should_skip_csv_unchanged(self, tmp_path):
        """Test returns True when CSV hash matches previous state."""
        csv_file = tmp_path / "test.csv"
        csv_content = "Title,Author\nBook 1,Author 1\n"
        csv_file.write_text(csv_content)

        # Calculate hash
        csv_hash = calculate_csv_hash(str(csv_file))

        # Create state file with matching hash
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": csv_hash,
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.STATE_FILE", state_file):
            should_skip, reason = should_skip_upload(str(csv_file))

        assert should_skip is True
        assert "unchanged since" in reason

    def test_should_skip_csv_changed(self, tmp_path):
        """Test returns False when CSV hash differs from previous state."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook 1\n")

        # Create state file with different hash
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": "different_hash_abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.STATE_FILE", state_file):
            should_skip, reason = should_skip_upload(str(csv_file))

        assert should_skip is False
        assert "changed" in reason

    def test_should_skip_force_overrides_unchanged(self, tmp_path):
        """Test force sync overrides unchanged CSV detection."""
        csv_file = tmp_path / "test.csv"
        csv_content = "Title\nBook\n"
        csv_file.write_text(csv_content)

        # Create state with matching hash
        csv_hash = calculate_csv_hash(str(csv_file))
        state_file = tmp_path / "state.json"
        state_data = {
            "last_hash": csv_hash,
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 1
        }
        state_file.write_text(json.dumps(state_data))

        with patch("sync.state.STATE_FILE", state_file):
            # Without force - should skip
            should_skip1, _ = should_skip_upload(str(csv_file), force_sync=False)
            # With force - should not skip
            should_skip2, _ = should_skip_upload(str(csv_file), force_sync=True)

        assert should_skip1 is True
        assert should_skip2 is False


class TestIntegration:
    """Integration tests for state management workflow."""

    def test_full_state_workflow(self, tmp_path):
        """Test complete workflow: save, load, compare."""
        state_file = tmp_path / "state.json"
        csv_file = tmp_path / "library.csv"
        csv_file.write_text("Title,Author\nBook 1,Author 1\n")

        with patch("sync.state.STATE_FILE", state_file):
            # Calculate hash
            csv_hash = calculate_csv_hash(str(csv_file))

            # Save state
            save_state(csv_hash=csv_hash, book_count=1)

            # Load state
            loaded_state = load_state()
            assert loaded_state is not None
            assert loaded_state["last_hash"] == csv_hash
            assert loaded_state["last_book_count"] == 1

            # Should skip upload (unchanged)
            should_skip, reason = should_skip_upload(str(csv_file))
            assert should_skip is True

    def test_detect_library_changes(self, tmp_path):
        """Test detection of library changes between syncs."""
        state_file = tmp_path / "state.json"
        csv_file = tmp_path / "library.csv"

        with patch("sync.state.STATE_FILE", state_file):
            # Initial sync
            csv_file.write_text("Title\nBook 1\n")
            hash1 = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=hash1, book_count=1)

            # Verify skip on unchanged
            should_skip1, _ = should_skip_upload(str(csv_file))
            assert should_skip1 is True

            # Modify library
            csv_file.write_text("Title\nBook 1\nBook 2\n")

            # Should detect change
            should_skip2, reason = should_skip_upload(str(csv_file))
            assert should_skip2 is False
            assert "changed" in reason

            # Save new state
            hash2 = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=hash2, book_count=2)

            # Now should skip again
            should_skip3, _ = should_skip_upload(str(csv_file))
            assert should_skip3 is True

    def test_state_persistence_across_runs(self, tmp_path):
        """Test state persists correctly across multiple runs."""
        state_file = tmp_path / "state.json"
        csv_file = tmp_path / "library.csv"
        csv_file.write_text("Title,Author\nBook,Author\n")

        with patch("sync.state.STATE_FILE", state_file):
            # First run
            hash1 = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=hash1, book_count=1)

            # Second run (simulated restart)
            state = load_state()
            assert state["last_hash"] == hash1

            # Third run (with same CSV)
            should_skip, _ = should_skip_upload(str(csv_file))
            assert should_skip is True
