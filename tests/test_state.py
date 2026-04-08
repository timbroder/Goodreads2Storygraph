"""Unit tests for state management and persistence."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sync.exceptions import StateError
from sync.models import BookRecord, DeltaResult
from sync.state import (
    _migrate_v1_to_v2,
    calculate_csv_hash,
    compute_delta,
    get_state_file,
    load_state,
    mark_book_failed,
    mark_book_synced,
    save_state,
    should_skip_upload,
)


class TestCalculateCSVHash:
    """Tests for CSV hash calculation."""

    def test_calculate_hash_valid_file(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title,Author\nBook,Author\n")
        hash_result = calculate_csv_hash(str(csv_file))
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64

    def test_calculate_hash_consistency(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title,Author\nTest Book,Test Author\n")
        assert calculate_csv_hash(str(csv_file)) == calculate_csv_hash(str(csv_file))

    def test_calculate_hash_different_content(self, tmp_path):
        f1 = tmp_path / "test1.csv"
        f2 = tmp_path / "test2.csv"
        f1.write_text("Title\nBook 1\n")
        f2.write_text("Title\nBook 2\n")
        assert calculate_csv_hash(str(f1)) != calculate_csv_hash(str(f2))

    def test_calculate_hash_missing_file(self):
        with pytest.raises(StateError, match="Failed to calculate hash"):
            calculate_csv_hash("/nonexistent/file.csv")


class TestMigration:
    """Tests for v1 -> v2 state migration."""

    def test_migrate_v1_to_v2(self):
        v1 = {
            "last_hash": "abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 42,
            "account_name": "default",
        }
        v2 = _migrate_v1_to_v2(v1)
        assert v2["schema_version"] == 2
        assert v2["last_csv_hash"] == "abc123"
        assert v2["books"] == {}
        assert v2["failed_books"] == {}
        assert v2["last_book_count"] == 42

    def test_load_state_auto_migrates_v1(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "last_hash": "abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 10,
            "account_name": "test",
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            result = load_state("test")
        assert result["schema_version"] == 2
        assert result["last_csv_hash"] == "abc123"
        assert result["books"] == {}


class TestLoadState:
    """Tests for state loading."""

    def test_load_state_missing_file(self, tmp_path):
        with patch("sync.state.get_state_file", return_value=tmp_path / "nonexistent.json"):
            assert load_state("test_account") is None

    def test_load_state_valid_v2(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_data = {
            "schema_version": 2,
            "last_csv_hash": "abc123",
            "last_sync_timestamp": "2024-01-01T00:00:00",
            "last_book_count": 42,
            "account_name": "test",
            "books": {"1": {"row_hash": "h1", "last_synced": "2024-01-01", "status": "synced"}},
            "failed_books": {},
        }
        state_file.write_text(json.dumps(state_data))
        with patch("sync.state.get_state_file", return_value=state_file):
            result = load_state("test")
        assert result["schema_version"] == 2
        assert "1" in result["books"]

    def test_load_state_corrupted_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("{invalid json")
        with patch("sync.state.get_state_file", return_value=state_file):
            with pytest.raises(StateError, match="corrupted"):
                load_state("test")


class TestSaveState:
    """Tests for state saving."""

    def test_save_state_creates_directory(self, tmp_path):
        state_file = tmp_path / "nested" / "dir" / "state.json"
        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="abc", book_count=10, account_name="test")
        assert state_file.exists()

    def test_save_state_v2_format(self, tmp_path):
        state_file = tmp_path / "state.json"
        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="xyz", book_count=25, account_name="test",
                       books={"1": {"row_hash": "h1"}}, failed_books={})
        data = json.loads(state_file.read_text())
        assert data["schema_version"] == 2
        assert data["last_csv_hash"] == "xyz"
        assert data["last_book_count"] == 25
        assert "1" in data["books"]
        assert "last_sync_timestamp" in data

    def test_save_state_preserves_books_when_not_provided(self, tmp_path):
        state_file = tmp_path / "state.json"
        # Write initial state with books
        initial = {
            "schema_version": 2,
            "last_csv_hash": "old",
            "last_sync_timestamp": "2024-01-01",
            "last_book_count": 5,
            "account_name": "test",
            "books": {"1": {"row_hash": "h1", "status": "synced"}},
            "failed_books": {},
        }
        state_file.write_text(json.dumps(initial))
        with patch("sync.state.get_state_file", return_value=state_file):
            # Save without specifying books — should preserve existing
            save_state(csv_hash="new", book_count=5, account_name="test")
        data = json.loads(state_file.read_text())
        assert data["last_csv_hash"] == "new"
        assert "1" in data["books"]  # preserved

    def test_save_state_atomic_write(self, tmp_path):
        state_file = tmp_path / "state.json"
        with patch("sync.state.get_state_file", return_value=state_file):
            save_state(csv_hash="hash", book_count=1, account_name="test")
        # Temp file should be cleaned up
        assert not (tmp_path / "state.tmp").exists()


class TestMarkBookSynced:
    """Tests for per-book sync tracking."""

    def test_mark_synced_creates_entry(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": "h",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": "test",
            "books": {},
            "failed_books": {},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            mark_book_synced("test", "12345", "rowhash1")
        data = json.loads(state_file.read_text())
        assert "12345" in data["books"]
        assert data["books"]["12345"]["row_hash"] == "rowhash1"
        assert data["books"]["12345"]["status"] == "synced"

    def test_mark_synced_removes_from_failed(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": "h",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": "test",
            "books": {},
            "failed_books": {"12345": {"row_hash": "old", "retry_count": 2, "error": "not found"}},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            mark_book_synced("test", "12345", "rowhash1")
        data = json.loads(state_file.read_text())
        assert "12345" in data["books"]
        assert "12345" not in data["failed_books"]

    def test_mark_synced_creates_state_if_missing(self, tmp_path):
        state_file = tmp_path / "state.json"
        with patch("sync.state.get_state_file", return_value=state_file):
            mark_book_synced("test", "999", "hash")
        data = json.loads(state_file.read_text())
        assert "999" in data["books"]


class TestMarkBookFailed:
    """Tests for per-book failure tracking."""

    def test_mark_failed_creates_entry(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": "h",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": "test",
            "books": {},
            "failed_books": {},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            mark_book_failed("test", "12345", "rowhash", "not found")
        data = json.loads(state_file.read_text())
        assert "12345" in data["failed_books"]
        assert data["failed_books"]["12345"]["retry_count"] == 1
        assert data["failed_books"]["12345"]["error"] == "not found"

    def test_mark_failed_increments_retry_count(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": "h",
            "last_sync_timestamp": "",
            "last_book_count": 0,
            "account_name": "test",
            "books": {},
            "failed_books": {"12345": {"row_hash": "old", "retry_count": 2, "error": "err", "last_attempt": ""}},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            mark_book_failed("test", "12345", "rowhash", "still failing")
        data = json.loads(state_file.read_text())
        assert data["failed_books"]["12345"]["retry_count"] == 3


class TestComputeDelta:
    """Tests for delta detection."""

    def _make_book(self, book_id="1", **overrides):
        defaults = dict(
            book_id=book_id, title="Test", author="Author",
            exclusive_shelf="read", my_rating=5,
            date_read="2024/01/01", date_added="2024/01/01", my_review="",
        )
        defaults.update(overrides)
        return BookRecord(**defaults)

    def test_all_new_when_no_state(self):
        books = {"1": self._make_book("1"), "2": self._make_book("2")}
        delta = compute_delta(books, None)
        assert len(delta.new_books) == 2
        assert len(delta.changed_books) == 0
        assert delta.unchanged_count == 0

    def test_all_unchanged(self):
        book = self._make_book("1")
        state = {
            "books": {"1": {"row_hash": book.row_hash(), "status": "synced"}},
            "failed_books": {},
        }
        delta = compute_delta({"1": book}, state)
        assert len(delta.new_books) == 0
        assert len(delta.changed_books) == 0
        assert delta.unchanged_count == 1
        assert delta.has_changes is False

    def test_detects_changed_book(self):
        book = self._make_book("1", my_rating=4)
        state = {
            "books": {"1": {"row_hash": "old_hash", "status": "synced"}},
            "failed_books": {},
        }
        delta = compute_delta({"1": book}, state)
        assert len(delta.changed_books) == 1
        assert delta.changed_books[0].book_id == "1"

    def test_detects_new_book(self):
        book = self._make_book("2")
        state = {
            "books": {"1": {"row_hash": "h1", "status": "synced"}},
            "failed_books": {},
        }
        delta = compute_delta({"1": self._make_book("1"), "2": book}, state)
        # book "1" needs its hash to match for unchanged
        assert len(delta.new_books) == 1
        assert delta.new_books[0].book_id == "2"

    def test_detects_removed_books(self):
        state = {
            "books": {
                "1": {"row_hash": "h1", "status": "synced"},
                "2": {"row_hash": "h2", "status": "synced"},
            },
            "failed_books": {},
        }
        # Only book 1 remains in CSV
        book1 = self._make_book("1")
        state["books"]["1"]["row_hash"] = book1.row_hash()
        delta = compute_delta({"1": book1}, state)
        assert "2" in delta.removed_book_ids

    def test_retryable_failed_books(self):
        book = self._make_book("1")
        state = {
            "books": {},
            "failed_books": {"1": {"row_hash": "old", "retry_count": 1, "error": "not found"}},
        }
        delta = compute_delta({"1": book}, state, max_retries=3)
        assert len(delta.retryable_books) == 1

    def test_skips_exceeded_retries(self):
        book = self._make_book("1")
        state = {
            "books": {},
            "failed_books": {"1": {"row_hash": "old", "retry_count": 3, "error": "not found"}},
        }
        delta = compute_delta({"1": book}, state, max_retries=3)
        assert len(delta.retryable_books) == 0
        assert len(delta.new_books) == 0

    def test_mixed_delta(self):
        book_unchanged = self._make_book("1")
        book_changed = self._make_book("2", my_rating=3)
        book_new = self._make_book("3")

        state = {
            "books": {
                "1": {"row_hash": book_unchanged.row_hash(), "status": "synced"},
                "2": {"row_hash": "old_hash", "status": "synced"},
                "4": {"row_hash": "h4", "status": "synced"},  # removed
            },
            "failed_books": {},
        }
        csv_books = {"1": book_unchanged, "2": book_changed, "3": book_new}
        delta = compute_delta(csv_books, state)
        assert delta.unchanged_count == 1
        assert len(delta.changed_books) == 1
        assert len(delta.new_books) == 1
        assert "4" in delta.removed_book_ids


class TestShouldSkipUpload:
    """Tests for skip upload logic."""

    def test_force_sync_never_skips(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        skip, reason = should_skip_upload(str(csv_file), "test", force_sync=True)
        assert skip is False

    def test_no_previous_state(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        with patch("sync.state.get_state_file", return_value=tmp_path / "nonexistent.json"):
            skip, reason = should_skip_upload(str(csv_file), "test")
        assert skip is False

    def test_csv_unchanged_v2_state(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        csv_hash = calculate_csv_hash(str(csv_file))
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": csv_hash,
            "last_sync_timestamp": "2024-01-01",
            "last_book_count": 1,
            "account_name": "test",
            "books": {},
            "failed_books": {},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            skip, reason = should_skip_upload(str(csv_file), "test")
        assert skip is True

    def test_csv_unchanged_v1_state(self, tmp_path):
        """Test backward compatibility with v1 state format."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        csv_hash = calculate_csv_hash(str(csv_file))
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "last_hash": csv_hash,
            "last_sync_timestamp": "2024-01-01",
            "last_book_count": 1,
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            skip, reason = should_skip_upload(str(csv_file), "test")
        # After migration, last_csv_hash is set from last_hash
        assert skip is True

    def test_csv_changed(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Title\nBook\n")
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "last_csv_hash": "different_hash",
            "last_sync_timestamp": "2024-01-01",
            "last_book_count": 1,
            "account_name": "test",
            "books": {},
            "failed_books": {},
        }))
        with patch("sync.state.get_state_file", return_value=state_file):
            skip, reason = should_skip_upload(str(csv_file), "test")
        assert skip is False


class TestIntegration:
    """Integration tests for state management workflow."""

    def test_full_v2_workflow(self, tmp_path):
        csv_file = tmp_path / "library.csv"
        csv_file.write_text("Title\nBook\n")
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            csv_hash = calculate_csv_hash(str(csv_file))
            save_state(csv_hash=csv_hash, book_count=1, account_name="test",
                       books={}, failed_books={})

            # Mark a book synced
            mark_book_synced("test", "12345", "rowhash1")

            # Load and verify
            state = load_state("test")
            assert state["schema_version"] == 2
            assert "12345" in state["books"]
            assert state["books"]["12345"]["status"] == "synced"

            # Skip check should work
            skip, _ = should_skip_upload(str(csv_file), "test")
            assert skip is True

    def test_failure_then_success_workflow(self, tmp_path):
        state_file = tmp_path / "state.json"

        with patch("sync.state.get_state_file", return_value=state_file):
            # First attempt fails
            mark_book_failed("test", "999", "hash", "not found")
            state = load_state("test")
            assert state["failed_books"]["999"]["retry_count"] == 1

            # Second attempt succeeds
            mark_book_synced("test", "999", "hash")
            state = load_state("test")
            assert "999" in state["books"]
            assert "999" not in state["failed_books"]
