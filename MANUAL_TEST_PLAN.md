# Goodreads2Storygraph - Comprehensive Manual Test Plan

**Date:** 2026-01-16
**Environment:** Claude Code CLI
**Python Version:** 3.14.2
**Mode:** Primarily single-account with limited multi-account testing

---

## Prerequisites

### Required Environment Variables

The following environment variables must be provided in a `.env` file:

```
# Single Account Credentials
GOODREADS_EMAIL=your-goodreads-email@example.com
GOODREADS_PASSWORD=your-goodreads-password
STORYGRAPH_EMAIL=your-storygraph-email@example.com
STORYGRAPH_PASSWORD=your-storygraph-password

# Optional Configuration
LOG_LEVEL=INFO
DRY_RUN=false
FORCE_SYNC=false
```

### Existing Test Data
- Goodreads account has books in various shelves (currently-reading, read, to-read, possibly custom shelves)
- One manual import has already been completed to StoryGraph
- Test accounts are ready on both platforms

---

## Test Environment Setup

### TS-001: Create Virtual Environment
**Objective:** Set up isolated Python environment

**Steps:**
1. Navigate to project root: `cd /home/user/Goodreads2Storygraph`
2. Create venv: `python3.14 -m venv venv`
3. Activate venv: `source venv/bin/activate`
4. Verify activation: `which python` should show venv path

**Expected Outcome:**
- Virtual environment created successfully
- Python executable points to venv
- Prompt shows `(venv)` prefix

**Success Criteria:**
- ✅ `venv/` directory exists
- ✅ `which python` returns `*/venv/bin/python`
- ✅ `python --version` shows `Python 3.14.2`

---

### TS-002: Install Dependencies
**Objective:** Install all required packages

**Steps:**
1. Check for requirements file: `ls requirements*.txt`
2. Install dependencies: `pip install -r requirements.txt` (or appropriate file)
3. Install Playwright browsers: `playwright install`
4. Verify installations: `pip list`

**Expected Outcome:**
- All packages installed without errors
- Playwright chromium browser downloaded
- Key packages visible: playwright, python-dotenv, etc.

**Success Criteria:**
- ✅ No installation errors
- ✅ `playwright` package present in `pip list`
- ✅ Playwright browsers installed successfully

---

### TS-003: Create Directory Structure
**Objective:** Set up required data directories

**Steps:**
1. Create base directories:
   ```bash
   mkdir -p data/logs/runs
   mkdir -p data/artifacts
   mkdir -p data/state
   mkdir -p data/config
   ```
2. Verify structure: `tree data/` or `find data/ -type d`
3. Check permissions: `ls -la data/`

**Expected Outcome:**
- All directories created successfully
- Proper read/write permissions set
- Directory structure matches expected layout

**Success Criteria:**
- ✅ `data/logs/runs/` exists
- ✅ `data/artifacts/` exists
- ✅ `data/state/` exists
- ✅ `data/config/` exists
- ✅ All directories writable

---

### TS-004: Verify Environment Configuration
**Objective:** Ensure .env file is properly configured

**Steps:**
1. Verify .env exists: `ls -la .env`
2. Check file is not committed: `git status .env` (should be ignored)
3. Validate structure (do not display credentials): `grep -E "^[A-Z_]+=" .env | wc -l`
4. Prompt user to confirm all required credentials are set

**Expected Outcome:**
- .env file exists and is gitignored
- Contains all required variables
- User confirms credentials are correct

**Success Criteria:**
- ✅ `.env` file exists
- ✅ File not tracked by git
- ✅ All required variables present
- ✅ User confirms credentials are valid

---

## CLI Discovery Tests

### TC-001: Discover Available Commands
**Objective:** Identify all CLI commands and options

**Steps:**
1. Run help command: `python -m sync.main --help`
2. Document all available flags and options
3. Check for config file options: look for account selection, dry-run, force, etc.
4. Identify entry points and modules

**Expected Outcome:**
- Help text displays all available commands
- Command-line flags documented
- Clear usage instructions shown

**Success Criteria:**
- ✅ Help command executes successfully
- ✅ Available options documented
- ✅ Usage examples provided (if any)

---

### TC-002: Validate CLI Arguments
**Objective:** Test CLI argument parsing

**Steps:**
1. Test invalid flag: `python -m sync.main --invalid-flag`
2. Test help variations: `-h`, `--help`
3. Test version (if available): `--version`
4. Document argument behavior

**Expected Outcome:**
- Invalid flags produce helpful error messages
- Help flags work correctly
- CLI provides clear feedback

**Success Criteria:**
- ✅ Invalid flags handled gracefully
- ✅ Error messages are clear and actionable
- ✅ Help system works properly

---

## Happy Path Tests (Single Account)

### TC-003: Initial Clean Sync
**Objective:** Perform first full sync with clean state

**Steps:**
1. Clear any existing state: `rm -rf data/state/*`
2. Clear artifacts: `rm -rf data/artifacts/*`
3. Run sync: `python -m sync.main`
4. Monitor console output for progress
5. Check for screenshots in appropriate directory
6. Wait for completion

**Expected Outcome:**
- Automated Goodreads export begins
- CSV file downloaded successfully
- Playwright navigates to StoryGraph
- Upload process completes
- Success message displayed
- Process exits with code 0

**Success Criteria:**
- ✅ Goodreads CSV exported to `data/artifacts/goodreads_export_*.csv`
- ✅ Log files created in `data/logs/runs/`
- ✅ State file created in `data/state/`
- ✅ No errors or warnings in logs (except expected ones)
- ✅ Screenshots captured during automation
- ✅ Exit code = 0
- ✅ User confirms books visible in StoryGraph web UI

**Verification Steps:**
1. Check artifacts: `ls -lh data/artifacts/`
2. Examine latest log: `tail -50 data/logs/runs/*.log`
3. Verify state file: `cat data/state/*.json` (check structure)
4. Count exported books: `wc -l data/artifacts/goodreads_export_*.csv`
5. User manually verifies StoryGraph website shows synced books

---

### TC-004: Incremental Sync (No Changes)
**Objective:** Test state tracking when nothing has changed

**Steps:**
1. Keep existing state from TC-003
2. Run sync again: `python -m sync.main`
3. Monitor for "no changes detected" logic

**Expected Outcome:**
- Tool detects no changes since last sync
- Minimal processing performed
- State preserved
- Exits successfully with appropriate message

**Success Criteria:**
- ✅ "No changes" or similar message in output
- ✅ No new export/upload performed (or minimal processing)
- ✅ State file timestamp/content appropriate
- ✅ Exit code = 0
- ✅ Logs indicate no-op or minimal work

---

### TC-005: Incremental Sync (With Changes)
**Objective:** Test delta sync functionality

**Steps:**
1. Prompt user to make a change in Goodreads (mark book as read, add to currently-reading, etc.)
2. User confirms change made
3. Run sync: `python -m sync.main`
4. Verify only delta is processed

**Expected Outcome:**
- Tool detects changes
- Exports updated data
- Syncs changes to StoryGraph
- State updated to reflect new sync

**Success Criteria:**
- ✅ Change detected in logs
- ✅ New export file created with updated data
- ✅ Upload completes successfully
- ✅ State file updated
- ✅ User confirms change visible in StoryGraph
- ✅ Exit code = 0

---

## CLI Options Testing

### TC-006: Dry Run Mode
**Objective:** Test dry-run functionality

**Steps:**
1. Run with dry-run flag: `python -m sync.main --dry-run` (or equivalent)
2. Monitor output for dry-run indicators
3. Check that no actual changes occur

**Expected Outcome:**
- Tool simulates sync process
- No actual upload to StoryGraph
- State not modified (or marked as dry-run)
- Clear indication this was a dry run

**Success Criteria:**
- ✅ Dry-run mode activated (shown in output)
- ✅ Export may occur, but no upload happens
- ✅ State unchanged or clearly marked as dry-run
- ✅ Logs indicate dry-run mode
- ✅ User confirms no changes in StoryGraph
- ✅ Exit code = 0

---

### TC-007: Force Sync Mode
**Objective:** Test force sync bypassing state checks

**Steps:**
1. With existing state from previous tests
2. Run with force flag: `python -m sync.main --force` (or equivalent)
3. Verify state checks bypassed

**Expected Outcome:**
- Tool ignores existing state
- Performs full sync regardless of changes
- New export and upload executed
- State updated/overwritten

**Success Criteria:**
- ✅ Force mode indicated in output
- ✅ Full sync performed despite no changes
- ✅ New artifacts created
- ✅ State updated
- ✅ Exit code = 0

---

### TC-008: Verbose Logging
**Objective:** Test verbose/debug logging modes

**Steps:**
1. Run with verbose flag: `python -m sync.main --verbose` or `--debug` (if available)
2. Or set `LOG_LEVEL=DEBUG` in .env and run
3. Examine output for increased detail

**Expected Outcome:**
- Detailed debug logs displayed
- More granular progress information
- Internal state and decisions logged

**Success Criteria:**
- ✅ Debug/verbose output visible
- ✅ More detailed than normal run
- ✅ Useful for troubleshooting
- ✅ Sync still completes successfully

---

### TC-009: All CLI Options Combined
**Objective:** Test combining multiple flags

**Steps:**
1. Identify compatible flag combinations
2. Run with multiple flags: e.g., `python -m sync.main --dry-run --verbose --force`
3. Verify flags work together correctly

**Expected Outcome:**
- Multiple flags respected simultaneously
- No conflicts or errors
- Behavior combines as expected

**Success Criteria:**
- ✅ All specified flags active
- ✅ Combined behavior logical
- ✅ No flag conflicts
- ✅ Exit code = 0

---

## State Management Tests

### TC-010: Clean State Full Sync
**Objective:** Verify behavior with no prior state

**Steps:**
1. Delete all state: `rm -rf data/state/*`
2. Keep artifacts intact
3. Run sync: `python -m sync.main`

**Expected Outcome:**
- Tool treats as initial sync
- Full export and upload performed
- New state file created

**Success Criteria:**
- ✅ Full sync performed
- ✅ New state file created
- ✅ Complete export generated
- ✅ Exit code = 0

---

### TC-011: Corrupted State Handling
**Objective:** Test recovery from invalid state file

**Steps:**
1. Manually corrupt state file: `echo "invalid json" > data/state/*.json`
2. Run sync: `python -m sync.main`
3. Observe error handling

**Expected Outcome:**
- Tool detects invalid state
- Either recovers gracefully (treats as clean slate) or exits with clear error
- User prompted or automatic recovery attempted

**Success Criteria:**
- ✅ Corruption detected
- ✅ Clear error message OR automatic recovery
- ✅ Sync can proceed (with or without state)
- ✅ Exit code appropriate (0 if recovered, non-zero if failed)

---

### TC-012: State File Permissions
**Objective:** Test behavior when state file not writable

**Steps:**
1. Make state directory read-only: `chmod 444 data/state/`
2. Run sync: `python -m sync.main`
3. Observe error handling

**Expected Outcome:**
- Tool detects write permission issue
- Clear error message displayed
- Graceful exit without corruption

**Success Criteria:**
- ✅ Permission error detected
- ✅ Clear, actionable error message
- ✅ No partial writes or corruption
- ✅ Non-zero exit code
- ✅ Restore permissions: `chmod 755 data/state/`

---

## Error Scenario Tests

### TC-013: Missing Export File
**Objective:** Handle missing or deleted export file

**Steps:**
1. Run sync and let export complete
2. During upload phase (or before), delete export CSV
3. Observe handling (or test by skipping export somehow)

**Alternative:** Test recovery if export step fails
- Simulate export failure if possible

**Expected Outcome:**
- Tool detects missing file
- Clear error message
- Graceful exit

**Success Criteria:**
- ✅ Missing file detected
- ✅ Error message indicates missing export
- ✅ Non-zero exit code
- ✅ No corruption or partial state

---

### TC-014: Network Interruption Simulation
**Objective:** Handle network issues during automation

**Note:** This may be difficult to simulate; can be skipped if not feasible

**Steps:**
1. If possible, simulate network issues (disconnect WiFi briefly during upload)
2. Or modify code to add artificial timeout
3. Observe error handling and retry logic

**Expected Outcome:**
- Tool detects network issue
- Retries or fails gracefully
- Clear error message

**Success Criteria:**
- ✅ Network error detected
- ✅ Appropriate error message
- ✅ Non-zero exit code or successful retry
- ✅ No corrupted state

---

### TC-015: Disk Space Exhaustion
**Objective:** Handle insufficient disk space

**Note:** May skip if too difficult to simulate safely

**Steps:**
1. Check available space: `df -h`
2. If safe, create large file to fill disk near capacity
3. Run sync and observe behavior

**Expected Outcome:**
- Tool detects write failure
- Clear error about disk space
- Graceful exit

**Success Criteria:**
- ✅ Write error detected
- ✅ Clear error message
- ✅ Non-zero exit code
- ✅ No partial/corrupted files

---

## Data Validation Tests

### TC-016: CSV Export Validation
**Objective:** Verify export CSV structure and content

**Steps:**
1. Run sync: `python -m sync.main`
2. Examine CSV: `head -20 data/artifacts/goodreads_export_*.csv`
3. Check structure:
   - Verify headers present
   - Validate required columns (Title, Author, ISBN, etc.)
   - Check for special characters handling
   - Verify row count matches expected

**Expected Outcome:**
- CSV properly formatted
- All expected columns present
- Data integrity maintained
- Special characters escaped properly

**Success Criteria:**
- ✅ Valid CSV structure
- ✅ Headers match Goodreads export format
- ✅ All books present in export
- ✅ No truncated or corrupted data
- ✅ Character encoding correct (UTF-8)

---

### TC-017: State File Validation
**Objective:** Verify state file structure and data

**Steps:**
1. After successful sync, examine state: `cat data/state/*.json | jq .`
2. Validate structure:
   - Last sync timestamp
   - Book count or hash
   - Account info (if stored)
   - Any other tracked metadata

**Expected Outcome:**
- Valid JSON structure
- Appropriate metadata stored
- Timestamps accurate
- Data matches expectations

**Success Criteria:**
- ✅ Valid JSON (parseable)
- ✅ Contains expected fields
- ✅ Timestamps reasonable
- ✅ Data consistent with actual sync

---

### TC-018: Log File Analysis
**Objective:** Comprehensive log review

**Steps:**
1. Run complete sync: `python -m sync.main`
2. Analyze logs: `cat data/logs/runs/*.log`
3. Check for:
   - Proper log levels (INFO, WARNING, ERROR)
   - Timestamps on each entry
   - Clear progress indicators
   - Any unexpected warnings
   - Error handling traces (if any errors occurred)
4. Verify log rotation (if multiple runs)

**Expected Outcome:**
- Clean, readable logs
- Appropriate log levels
- Complete trace of operations
- No unexpected errors

**Success Criteria:**
- ✅ Logs properly formatted
- ✅ Timestamps present
- ✅ Log levels appropriate
- ✅ No ERROR entries (except in error tests)
- ✅ Progress clearly documented
- ✅ Sensitive data not logged (passwords, etc.)

---

### TC-019: Screenshot Validation
**Objective:** Verify Playwright screenshots captured

**Steps:**
1. After sync with screenshots, locate screenshot directory
2. View screenshots: `ls -lh <screenshot-dir>/`
3. Open and examine key screenshots:
   - Goodreads login/export page
   - StoryGraph upload page
   - Confirmation/success page

**Expected Outcome:**
- Screenshots captured at key steps
- Images clear and viewable
- Proper naming/organization
- Sufficient for debugging

**Success Criteria:**
- ✅ Screenshots exist
- ✅ Files are valid images (can be opened)
- ✅ Show expected pages/states
- ✅ Useful for verification and debugging

---

## Edge Cases and Special Scenarios

### TC-020: Large Library Sync
**Objective:** Test with current library size

**Steps:**
1. Count books in Goodreads: prompt user
2. Run sync: `python -m sync.main`
3. Monitor performance and memory usage: `time python -m sync.main`
4. Verify all books synced

**Expected Outcome:**
- Sync completes successfully regardless of library size
- Reasonable performance
- All books processed

**Success Criteria:**
- ✅ Sync completes without timeout
- ✅ Memory usage reasonable
- ✅ All books in export CSV
- ✅ User confirms all books in StoryGraph
- ✅ Exit code = 0

---

### TC-021: Special Characters in Book Data
**Objective:** Verify handling of special characters

**Steps:**
1. Review current library for books with special characters:
   - Non-ASCII characters (accents, umlauts, etc.)
   - Quotes and apostrophes in titles
   - Ampersands, colons, etc.
2. Run sync: `python -m sync.main`
3. Verify these books sync correctly
4. User checks specific books in StoryGraph

**Expected Outcome:**
- Special characters preserved
- No encoding errors
- Books display correctly in StoryGraph

**Success Criteria:**
- ✅ No encoding errors in logs
- ✅ Special characters in CSV correct
- ✅ User confirms books display properly in StoryGraph
- ✅ Exit code = 0

---

### TC-022: Books on Custom Shelves
**Objective:** Test handling of custom shelves

**Steps:**
1. Prompt user if they have custom shelves
2. If yes, identify which books are on custom shelves
3. Run sync: `python -m sync.main`
4. Verify custom shelf books included
5. User checks these books in StoryGraph

**Expected Outcome:**
- Custom shelf books included in export
- Proper shelf mapping (if applicable)
- All books synced

**Success Criteria:**
- ✅ Custom shelves recognized
- ✅ Books from custom shelves in export
- ✅ User confirms books in StoryGraph
- ✅ Exit code = 0

---

### TC-023: Books with Missing Data
**Objective:** Handle books with incomplete metadata

**Steps:**
1. Identify books with missing data (no ISBN, no author, etc.)
2. Run sync: `python -m sync.main`
3. Verify these books handled gracefully

**Expected Outcome:**
- Books with missing data included
- No sync failures due to missing fields
- Appropriate handling/warnings logged

**Success Criteria:**
- ✅ Books with missing data in export
- ✅ No crashes or errors
- ✅ Appropriate warnings in logs (if any)
- ✅ User confirms books in StoryGraph
- ✅ Exit code = 0

---

### TC-024: Repeated Syncs Idempotency
**Objective:** Verify multiple syncs don't cause issues

**Steps:**
1. Run sync 3 times in succession:
   ```bash
   python -m sync.main
   python -m sync.main
   python -m sync.main
   ```
2. Verify each behaves correctly
3. Check for state accumulation issues
4. User verifies no duplication in StoryGraph

**Expected Outcome:**
- First sync processes fully
- Subsequent syncs detect no changes
- No duplication or state corruption
- StoryGraph shows books only once

**Success Criteria:**
- ✅ First sync succeeds
- ✅ Subsequent syncs are no-ops or minimal
- ✅ State consistent across runs
- ✅ No duplicates in StoryGraph (user confirms)
- ✅ Exit code = 0 for all

---

## Multi-Account Tests (Limited)

### TC-025: Multi-Account Setup
**Objective:** Configure multi-account mode

**Steps:**
1. Create accounts config: `cp accounts.example.json data/config/accounts.json`
2. Prompt user to edit with their credentials (if they have multiple accounts)
3. Validate JSON structure: `cat data/config/accounts.json | jq .`
4. Verify at least 2 accounts configured

**Expected Outcome:**
- Config file created
- Valid JSON structure
- Multiple accounts configured

**Success Criteria:**
- ✅ `data/config/accounts.json` exists
- ✅ Valid JSON
- ✅ At least 2 accounts present
- ✅ Required fields for each account

---

### TC-026: Multi-Account Sync (All Accounts)
**Objective:** Sync all configured accounts

**Steps:**
1. Clear all state: `rm -rf data/state/*`
2. Run multi-account sync: `python -m sync.main --accounts` (or however it's invoked)
3. Monitor output for each account
4. Verify separate state/artifacts per account

**Expected Outcome:**
- Each account synced in sequence
- Separate state files maintained
- All accounts succeed

**Success Criteria:**
- ✅ All accounts processed
- ✅ Separate state/artifacts per account
- ✅ User confirms syncs for all accounts in respective StoryGraph accounts
- ✅ Exit code = 0

---

### TC-027: Multi-Account Sync (Single Account)
**Objective:** Sync one specific account from config

**Steps:**
1. Run with account selector: `python -m sync.main --account my_account` (or equivalent)
2. Verify only specified account synced

**Expected Outcome:**
- Only specified account processed
- Other accounts untouched
- Correct credentials used

**Success Criteria:**
- ✅ Only specified account synced
- ✅ Correct state/artifacts created
- ✅ User confirms correct StoryGraph account updated
- ✅ Exit code = 0

---

## Post-Testing Validation

### TC-028: Complete System Verification
**Objective:** Final end-to-end verification

**Steps:**
1. User manually reviews StoryGraph library
2. Compare with Goodreads library
3. Spot-check various books, shelves, ratings
4. Verify sync date/metadata

**Expected Outcome:**
- Complete sync confirmed
- All data accurate
- No obvious missing books
- System working as expected

**Success Criteria:**
- ✅ User confirms library matches Goodreads
- ✅ All shelves represented
- ✅ Ratings and reviews (if synced) correct
- ✅ Overall system functioning properly

---

### TC-029: Cleanup and Documentation
**Objective:** Clean up test artifacts and document results

**Steps:**
1. Review all logs for any warnings or issues
2. Document any anomalies found
3. Optionally clean up test data: `rm -rf data/`
4. Deactivate venv: `deactivate`

**Expected Outcome:**
- Test results documented
- System in clean state
- Any issues noted for fixing

**Success Criteria:**
- ✅ All test results documented
- ✅ Issues tracked (if any)
- ✅ System ready for production use

---

## Summary Checklist

### Required Pre-Test Setup
- [ ] Python 3.14.2 installed
- [ ] `.env` file configured with valid credentials
- [ ] Test accounts prepared on Goodreads and StoryGraph
- [ ] Goodreads account has books in various shelves

### Environment Setup (TS-001 to TS-004)
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (pip packages)
- [ ] Playwright browsers installed
- [ ] Directory structure created
- [ ] Environment variables verified

### CLI Discovery (TC-001 to TC-002)
- [ ] Help command tested
- [ ] Available options documented
- [ ] Argument parsing validated

### Happy Path Tests (TC-003 to TC-005)
- [ ] Initial clean sync successful
- [ ] Incremental sync (no changes) works
- [ ] Incremental sync (with changes) works

### CLI Options (TC-006 to TC-009)
- [ ] Dry-run mode tested
- [ ] Force sync mode tested
- [ ] Verbose logging tested
- [ ] Combined options tested

### State Management (TC-010 to TC-012)
- [ ] Clean state sync tested
- [ ] Corrupted state handling verified
- [ ] Permission errors handled

### Error Scenarios (TC-013 to TC-015)
- [ ] Missing export file handled
- [ ] Network interruption handled (if tested)
- [ ] Disk space handled (if tested)

### Data Validation (TC-016 to TC-019)
- [ ] CSV export validated
- [ ] State file validated
- [ ] Log files analyzed
- [ ] Screenshots verified

### Edge Cases (TC-020 to TC-024)
- [ ] Large library sync successful
- [ ] Special characters handled
- [ ] Custom shelves tested
- [ ] Missing data handled
- [ ] Repeated syncs are idempotent

### Multi-Account (TC-025 to TC-027)
- [ ] Multi-account config setup
- [ ] All accounts sync tested
- [ ] Single account selector tested

### Final Validation (TC-028 to TC-029)
- [ ] Complete system verification
- [ ] Cleanup and documentation

---

## Test Execution Notes

### Execution Sequence
Tests should be executed in order as listed, since some tests depend on state from previous tests.

### Failure Handling
If any test fails, STOP immediately and investigate/fix the issue before proceeding.

### User Involvement
User will be prompted to:
- Confirm manual changes in Goodreads (TC-005)
- Verify sync results in StoryGraph browser (multiple tests)
- Provide library size information (TC-020)
- Check specific books with special scenarios (TC-021 to TC-023)
- Final verification of complete sync (TC-028)

### Test Duration
Estimated total time: 2-4 hours depending on:
- Library size
- Network speed
- Number of errors encountered
- Multi-account testing scope

---

## Success Criteria Summary

The test plan is considered successful when:

1. ✅ All setup tests pass (TS-001 to TS-004)
2. ✅ All happy path tests pass (TC-003 to TC-005)
3. ✅ All CLI options work as expected (TC-006 to TC-009)
4. ✅ State management works correctly (TC-010 to TC-012)
5. ✅ Error scenarios handled gracefully (TC-013 to TC-015)
6. ✅ Data validation confirms integrity (TC-016 to TC-019)
7. ✅ Edge cases handled properly (TC-020 to TC-024)
8. ✅ Basic multi-account functionality works (TC-025 to TC-027)
9. ✅ User confirms complete and accurate sync in StoryGraph
10. ✅ No critical issues or data loss observed

---

## Notes and Observations

(Space for recording observations, issues, or notes during testing)

-
-
-

**End of Test Plan**
