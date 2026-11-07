import os
import sys


def pytest_sessionfinish(session, exitstatus):
    """Skip interpreter teardown: Qt/torch objects crash on exit ("pure virtual
    method called") after every test has already passed, turning CI red."""
    if os.environ.get("CAMPUSGUARD_TEST_CLEAN_EXIT") == "1":
        return
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(int(exitstatus))
