"""Customer sign-in against the CampusGuard website's Supabase accounts.

Flow (mirrors the website): sign in with email + password through Supabase
Auth, then ask the website's ``/api/access-status`` endpoint whether the
account's application is approved. Only approved accounts may use the app.

The refresh token is kept in the OS credential vault (never on disk in plain
text) so users stay signed in between launches.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from campusguard import auth_config

_USER_AGENT = "CampusGuard-Desktop/1.0"
_TIMEOUT = 12.0
SESSION_SERVICE = "CampusGuard account"
SESSION_KEY = "session"


class AuthError(Exception):
    """A problem the user can read, e.g. wrong password or pending approval."""

    def __init__(self, message: str, *, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind  # "error" | "pending" | "rejected" | "missing"


class NetworkError(AuthError):
    """The server could not be reached (offline, DNS, timeout, 5xx)."""

    def __init__(self, message: str = "Could not reach CampusGuard. Check your internet connection and try again.") -> None:
        super().__init__(message, kind="network")


@dataclass(frozen=True)
class Session:
    email: str
    access_token: str
    refresh_token: str


def _request(url: str, *, method: str = "GET", payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", _USER_AGENT)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise NetworkError() from error
    try:
        parsed = json.loads(body.decode("utf-8")) if body else {}
    except (ValueError, UnicodeDecodeError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return status, parsed


def _supabase_headers() -> dict:
    return {"apikey": auth_config.SUPABASE_PUBLISHABLE_KEY}


def _session_from(payload: dict, fallback_email: str = "") -> Session:
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
        raise AuthError("Sign-in returned an unexpected response. Please try again.")
    return Session(email=str(user.get("email") or fallback_email), access_token=access, refresh_token=refresh)


def sign_in(email: str, password: str) -> Session:
    email = email.strip()
    if not email or not password:
        raise AuthError("Enter your email and password.")
    status, body = _request(
        f"{auth_config.SUPABASE_URL}/auth/v1/token?grant_type=password",
        method="POST",
        payload={"email": email, "password": password},
        headers=_supabase_headers(),
    )
    if status == 200:
        return _session_from(body, email)
    if status >= 500 or status == 429:
        raise NetworkError("CampusGuard sign-in is busy right now. Please try again in a minute.")
    code = str(body.get("error_code") or body.get("code") or "")
    if code == "email_not_confirmed":
        raise AuthError("Please confirm your email address first, then sign in.")
    raise AuthError("Email or password is incorrect. If you have not applied yet, request early access first.")


def refresh_session(refresh_token: str) -> Session:
    status, body = _request(
        f"{auth_config.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        method="POST",
        payload={"refresh_token": refresh_token},
        headers=_supabase_headers(),
    )
    if status == 200:
        return _session_from(body)
    if status >= 500 or status == 429:
        raise NetworkError()
    raise AuthError("Your saved sign-in has expired. Please sign in again.")


def check_access(access_token: str) -> None:
    """Return normally only when the account is approved; raise AuthError otherwise."""
    status, body = _request(
        f"{auth_config.WEBSITE_URL}/api/access-status",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if status == 200:
        decision = body.get("status")
        if decision == "approved":
            return
        if decision == "pending":
            raise AuthError(
                "Your application is still pending review. You can sign in after the CampusGuard team approves it.",
                kind="pending",
            )
        if decision == "rejected":
            raise AuthError(
                "Your application has not been approved. Please contact the CampusGuard team if you need help.",
                kind="rejected",
            )
        raise AuthError("We could not verify your access status. Please try again.")
    if status == 403 and body.get("status") == "missing":
        raise AuthError(
            "This account does not have a linked access application. Please request early access.",
            kind="missing",
        )
    if status == 401:
        raise AuthError("Your session is invalid. Please sign in again.")
    if status >= 500 or status in (0, 429):
        raise NetworkError("We could not verify your access right now. Please try again in a moment.")
    raise AuthError("We could not verify your access status. Please try again.")


def request_password_reset(email: str) -> None:
    email = email.strip()
    if not email:
        raise AuthError("Enter your account email first.")
    status, _body = _request(
        f"{auth_config.SUPABASE_URL}/auth/v1/recover",
        method="POST",
        payload={"email": email, "redirect_to": f"{auth_config.WEBSITE_URL}/reset-password"},
        headers=_supabase_headers(),
    )
    if status >= 500 or status == 429:
        raise NetworkError("We could not send the reset email right now. Please try again shortly.")
    # Deliberately identical for existing and unknown emails (no account probing).


def login(email: str, password: str) -> Session:
    """Full sign-in: credentials first, then website approval."""
    session = sign_in(email, password)
    check_access(session.access_token)
    return session


# --------------------------------------------------------------------------
# Remembered session
# --------------------------------------------------------------------------

def _keyring():
    import keyring  # imported lazily: keeps start-up light and tests mockable

    return keyring


def save_session(session: Session, *, now: float | None = None) -> None:
    payload = json.dumps(
        {
            "email": session.email,
            "refresh_token": session.refresh_token,
            "verified_at": now if now is not None else time.time(),
        }
    )
    try:
        _keyring().set_password(SESSION_SERVICE, SESSION_KEY, payload)
    except Exception:
        pass  # Not remembering the sign-in is acceptable; signing in still works.


def load_saved() -> dict | None:
    try:
        raw = _keyring().get_password(SESSION_SERVICE, SESSION_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("refresh_token"), str):
        return None
    return data


def clear_saved() -> None:
    try:
        _keyring().delete_password(SESSION_SERVICE, SESSION_KEY)
    except Exception:
        pass


def resume(now: Callable[[], float] = time.time) -> Session | None:
    """Try to continue the remembered session without asking for a password.

    Returns a Session when the user may proceed, or None when they must sign
    in. A network failure keeps the user signed in for OFFLINE_GRACE_SECONDS
    after the last successful check; a rejected/expired session is forgotten.
    """
    saved = load_saved()
    if not saved:
        return None
    email = str(saved.get("email") or "")
    verified_at = float(saved.get("verified_at") or 0)
    offline_ok = (now() - verified_at) < auth_config.OFFLINE_GRACE_SECONDS
    try:
        session = refresh_session(saved["refresh_token"])
    except NetworkError:
        if offline_ok:
            return Session(email=email, access_token="", refresh_token=saved["refresh_token"])
        return None
    except AuthError:
        clear_saved()
        return None
    try:
        check_access(session.access_token)
    except NetworkError:
        # Supabase rotates refresh tokens, so keep the new one even though the
        # approval check could not run; verified_at stays at its old value.
        save_session(session, now=verified_at)
        return session if offline_ok else None
    except AuthError:
        clear_saved()
        return None
    save_session(session, now=now())
    return session
