"""Public connection settings for CampusGuard customer sign-in.

The Supabase URL and *publishable* key are designed to be public: they only
identify the project, and every request is still checked by Supabase's own
access rules. No secret/service-role key belongs in the desktop app.

Environment variables override these defaults, which helps testing a staging
project without rebuilding.
"""

from __future__ import annotations

import os

SUPABASE_URL = os.environ.get("CAMPUSGUARD_SUPABASE_URL", "https://dvvrhjvpsfsgaptkjowx.supabase.co").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get(
    "CAMPUSGUARD_SUPABASE_KEY", "sb_publishable_i4CgKj1R3kaU3Rl2TaEPrw_kXd6BKWH"
)
WEBSITE_URL = os.environ.get("CAMPUSGUARD_WEBSITE_URL", "https://campusguardweb.vercel.app").rstrip("/")

# After a successful sign-in the app keeps working offline for this long, so a
# network outage does not lock a campus out of its cameras.
OFFLINE_GRACE_SECONDS = 7 * 24 * 60 * 60
