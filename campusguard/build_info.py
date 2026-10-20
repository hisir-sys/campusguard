"""Build identity for CampusGuard.

Local/source runs use "dev". The Windows release workflow injects a numeric
build version through the CAMPUSGUARD_VERSION environment variable.
"""

import os

try:  # written by the release workflow right before the app is frozen
    from campusguard._build_version import VERSION as _BAKED_VERSION
except ImportError:
    _BAKED_VERSION = ""

BUILD_VERSION = _BAKED_VERSION or os.environ.get("CAMPUSGUARD_VERSION", "dev")
APP_NAME = "CampusGuard"
GITHUB_REPOSITORY = "hisir-sys/campusguard"
RELEASE_TAG = "latest"
