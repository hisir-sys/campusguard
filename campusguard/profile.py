"""The account details (name, school, phone, alert numbers) shared with the website and phone app.

They are stored on the website account, so editing them in any of the three places changes all three.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from campusguard import auth, auth_config

TIMEOUT_SECONDS = 15.0
_USER_AGENT = "CampusGuard-Desktop/1.0"
MAX_ALERT_NUMBERS = 5


class ProfileError(Exception):
    """A message that is safe to show to the user."""


def _call(method: str, payload: dict | None = None) -> dict:
    token = auth.fresh_access_token()
    if not token:
        raise ProfileError("Sign in again to edit your account.")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        auth_config.WEBSITE_URL + "/api/profile", data=body, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read(65536).decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read(4096).decode("utf-8")).get("error")
        except Exception:  # noqa: BLE001
            message = None
        error.close()
        raise ProfileError(message or "Could not reach your account. Try again in a moment.") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ProfileError("Could not reach CampusGuard. Check your internet connection.") from None


def fetch_profile() -> dict:
    return _call("GET")


def save_profile(full_name: str, school_name: str, phone: str, alert_phones: list[str]) -> dict:
    return _call("PUT", {"full_name": full_name, "school_name": school_name, "phone": phone,
                         "alert_phones": [n for n in (x.strip() for x in alert_phones) if n][:MAX_ALERT_NUMBERS]})
