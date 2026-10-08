"""Build identity for CampusGuard.

Local/source runs use "dev". The Windows release workflow injects a numeric
build version through the CAMPUSGUARD_VERSION environment variable.
"""

import os

BUILD_VERSION = os.environ.get("CAMPUSGUARD_VERSION", "dev")
APP_NAME = "CampusGuard"
GITHUB_REPOSITORY = "hisir-sys/campusguard"
RELEASE_TAG = "latest"
