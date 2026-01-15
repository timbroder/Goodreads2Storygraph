# Test Suite Documentation

## Overview

This directory contains the unit test suite for the Goodreads2Storygraph sync service. The tests validate core functionality including CSV validation, hash calculation, state management, and persistence logic.

## Test Structure

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Shared pytest fixtures
├── test_transform.py        # CSV validation and transformation tests
└── test_state.py            # State management and persistence tests
```

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_transform.py -v
pytest tests/test_state.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_transform.py::TestValidateCSV -v
```

### Run Specific Test Method
```bash
pytest tests/test_transform.py::TestValidateCSV::test_validate_valid_csv -v
```

### Run with Coverage
```bash
pytest tests/ --cov=sync --cov-report=html
```

## Test Coverage

### test_transform.py
Tests for CSV validation, hashing, and book counting:

- **TestValidateCSV**: CSV validation logic
  - Valid CSV format validation
  - Missing file error handling
  - Empty file detection
  - Header-only file detection
  - Missing expected columns validation
  - Malformed CSV handling

- **TestCalculateHash**: Hash calculation
  - Consistency across multiple calculations
  - Different content produces different hashes
  - SHA256 format validation
  - Large file handling

- **TestCountBooks**: Book counting logic
  - Single and multiple book counting
  - Empty CSV handling
  - Large library support
  - Missing file error handling

- **TestIntegration**: Combined workflow tests
  - Full CSV workflow (validate → hash → count)
  - CSV change detection

**Total: 20 tests**

### test_state.py
Tests for state management and persistence:

- **TestCalculateCSVHash**: CSV hash calculation
  - Valid file hashing
  - Hash consistency
  - Different content detection
  - Missing file error handling
  - Large file support

- **TestLoadState**: State loading
  - Missing file handling (returns None)
  - Valid state loading
  - Missing required keys validation
  - Corrupted JSON handling
  - Extra fields acceptance

- **TestSaveState**: State saving
  - Directory creation
  - Valid content structure
  - Overwriting existing state
  - Timestamp format validation

- **TestShouldSkipUpload**: Upload skip logic
  - Force sync override
  - No previous state handling
  - Unchanged CSV detection
  - Changed CSV detection
  - Force sync overrides unchanged detection

- **TestIntegration**: State workflow tests
  - Full state workflow (save → load → compare)
  - Library change detection across syncs
  - State persistence across multiple runs

**Total: 22 tests**

## Test Fixtures

### conftest.py
Shared fixtures available to all tests:

- `tmp_path`: Temporary directory for test files
- `sample_csv`: Pre-populated sample CSV file for testing

## Test Requirements

All test dependencies are listed in `requirements.txt`:
- `pytest==7.4.3` - Test framework
- Required for mocking browser interactions

## Manual Testing Checklist

In addition to automated tests, the following manual tests should be performed:

### Module Import Test
```bash
python -c "import sync; from sync import main; print('Success')"
```

### Module Invocation Test
```bash
python -m sync.main
# Should fail with missing browser/credentials, but validates structure
```

### Docker Build Test
```bash
docker build -f docker/Dockerfile -t goodreads2storygraph:test .
```

### Docker Compose Test
```bash
# With valid .env file
docker compose up -d
docker logs goodreads2storygraph-sync
docker compose down
```

### End-to-End Test (Requires Valid Credentials)
```bash
# 1. Manual sync
docker exec goodreads2storygraph-sync python -m sync.main

# 2. Dry run mode
docker exec goodreads2storygraph-sync sh -c "DRY_RUN=true python -m sync.main"

# 3. Force full sync
docker exec goodreads2storygraph-sync sh -c "FORCE_FULL_SYNC=true python -m sync.main"

# 4. Verify logs
tail -f data/logs/sync.log
ls data/logs/runs/

# 5. Verify artifacts
ls data/artifacts/
ls data/state/

# 6. Verify cron scheduling
docker exec goodreads2storygraph-sync crontab -l
```

## Test Results

### Phase 4 Test Results
- **Unit Tests**: ✅ 42/42 passed
- **Module Imports**: ✅ All modules import successfully
- **Module Invocation**: ✅ Main module can be invoked
- **Docker Build**: ⚠️  Cannot test (Docker not available in test environment)
- **Container Startup**: ⚠️  Cannot test (Docker not available in test environment)

### Notes
- Docker tests should be performed in an environment with Docker installed
- End-to-end tests require valid Goodreads and StoryGraph credentials
- Browser automation requires Playwright browsers to be installed: `playwright install chromium`

## Continuous Integration

For CI/CD pipelines, recommended test command:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests with coverage
pytest tests/ -v --cov=sync --cov-report=xml --cov-report=term

# Run linting (if configured)
# pylint sync/
# black --check sync/
# mypy sync/
```

## Future Test Improvements

1. **Integration Tests**: Add tests for Goodreads and StoryGraph clients using mock Playwright interactions
2. **E2E Tests**: Add end-to-end tests with test fixtures/accounts
3. **Performance Tests**: Add tests for large CSV files (10k+ books)
4. **Error Scenario Tests**: More comprehensive error handling tests
5. **Cron Tests**: Validate cron schedule parsing and timing
6. **Docker Tests**: Automated Docker build and container tests in CI

## Contributing

When adding new features:
1. Write tests first (TDD approach)
2. Ensure all existing tests pass
3. Add new test cases for new functionality
4. Update this README with new test descriptions
5. Maintain >80% code coverage
