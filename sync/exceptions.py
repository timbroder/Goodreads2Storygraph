"""Custom exception classes for the sync package."""


class SyncError(Exception):
    """Base exception for all sync-related errors."""
    pass


class GoodreadsExportError(SyncError):
    """Failed to export or download Goodreads library."""
    pass


class StoryGraphUploadError(SyncError):
    """Failed to upload or verify upload to StoryGraph."""
    pass


class StateError(SyncError):
    """State file corruption or access issues."""
    pass


class PlaywrightError(SyncError):
    """Browser automation failures."""
    pass
