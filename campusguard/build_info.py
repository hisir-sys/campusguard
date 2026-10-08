"""Build identity for CampusGuard.

The release workflow temporarily replaces BUILD_VERSION with the generated
Windows release number before packaging. Local/source runs intentionally use
"dev".
"""

BUILD_VERSION = "dev"
APP_NAME = "CampusGuard"
GITHUB_REPOSITORY = "hisir-sys/campusguard"
RELEASE_TAG = "latest"
