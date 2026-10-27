from __future__ import annotations

import json

import pytest

from campusguard import auth, auth_config
from campusguard.updater import select_update

OK_TOKEN = {"access_token": "acc", "refresh_token": "ref", "user": {"email": "a@b.org"}}


class FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def get_password(self, service, key):
        return self.store.get((service, key))

    def delete_password(self, service, key):
        self.store.pop((service, key), None)


@pytest.fixture()
def keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "_keyring", lambda: fake)
    return fake


def script(monkeypatch, responses):
    """Replace the HTTP layer; each call pops the next (status, body) or raises it."""
    calls = []

    def fake_request(url, **kwargs):
        calls.append((url, kwargs))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(auth, "_request", fake_request)
    return calls


def test_login_success_checks_website_approval(monkeypatch):
    calls = script(monkeypatch, [(200, OK_TOKEN), (200, {"status": "approved"})])
    session = auth.login(" a@b.org ", "secret-password")
    assert session.email == "a@b.org" and session.refresh_token == "ref"
    assert calls[0][0].startswith(auth_config.SUPABASE_URL + "/auth/v1/token?grant_type=password")
    assert calls[0][1]["payload"] == {"email": "a@b.org", "password": "secret-password"}
    assert calls[0][1]["headers"]["apikey"] == auth_config.SUPABASE_PUBLISHABLE_KEY
    assert calls[1][0] == auth_config.WEBSITE_URL + "/api/access-status"
    assert calls[1][1]["headers"]["Authorization"] == "Bearer acc"


def test_wrong_password(monkeypatch):
    script(monkeypatch, [(400, {"error_code": "invalid_credentials"})])
    with pytest.raises(auth.AuthError) as info:
        auth.login("a@b.org", "nope")
    assert "incorrect" in str(info.value)


def test_unconfirmed_email(monkeypatch):
    script(monkeypatch, [(400, {"error_code": "email_not_confirmed"})])
    with pytest.raises(auth.AuthError) as info:
        auth.login("a@b.org", "x")
    assert "confirm your email" in str(info.value)


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (200, {"status": "pending"}, "pending"),
        (200, {"status": "rejected"}, "rejected"),
        (403, {"status": "missing", "error": "x"}, "missing"),
    ],
)
def test_not_approved(monkeypatch, status, body, kind):
    script(monkeypatch, [(200, OK_TOKEN), (status, body)])
    with pytest.raises(auth.AuthError) as info:
        auth.login("a@b.org", "pw")
    assert info.value.kind == kind


def test_empty_fields_do_not_hit_network(monkeypatch):
    calls = script(monkeypatch, [])
    with pytest.raises(auth.AuthError):
        auth.login("", "")
    assert calls == []


def test_network_error_is_distinguished(monkeypatch):
    script(monkeypatch, [auth.NetworkError()])
    with pytest.raises(auth.NetworkError):
        auth.login("a@b.org", "pw")


def test_password_reset_never_reveals_account(monkeypatch):
    calls = script(monkeypatch, [(200, {}), (400, {"msg": "unknown"})])
    auth.request_password_reset("a@b.org")
    auth.request_password_reset("nobody@b.org")  # no exception either way
    assert calls[0][1]["payload"]["redirect_to"] == auth_config.WEBSITE_URL + "/reset-password"


def test_resume_without_saved_session(monkeypatch, keyring):
    assert auth.resume() is None


def test_resume_success_rotates_and_saves(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    new = {"access_token": "acc2", "refresh_token": "new", "user": {"email": "a@b.org"}}
    script(monkeypatch, [(200, new), (200, {"status": "approved"})])
    session = auth.resume(now=lambda: 2000)
    assert session and session.refresh_token == "new"
    saved = auth.load_saved()
    assert saved["refresh_token"] == "new" and saved["verified_at"] == 2000


def test_resume_offline_within_grace_keeps_user_in(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    script(monkeypatch, [auth.NetworkError()])
    session = auth.resume(now=lambda: 1000 + 3600)
    assert session and session.email == "a@b.org"
    assert auth.load_saved() is not None


def test_resume_offline_after_grace_requires_login(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    script(monkeypatch, [auth.NetworkError()])
    assert auth.resume(now=lambda: 1000 + auth_config.OFFLINE_GRACE_SECONDS + 1) is None


def test_resume_expired_session_is_forgotten(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    script(monkeypatch, [(400, {"error": "invalid_grant"})])
    assert auth.resume(now=lambda: 2000) is None
    assert auth.load_saved() is None


def test_resume_revoked_access_is_forgotten(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    script(monkeypatch, [(200, OK_TOKEN), (200, {"status": "rejected"})])
    assert auth.resume(now=lambda: 2000) is None
    assert auth.load_saved() is None


def test_resume_keeps_rotated_token_when_check_is_offline(monkeypatch, keyring):
    auth.save_session(auth.Session("a@b.org", "", "old"), now=1000)
    script(monkeypatch, [(200, OK_TOKEN), auth.NetworkError()])
    assert auth.resume(now=lambda: 2000) is not None
    saved = auth.load_saved()
    assert saved["refresh_token"] == "ref" and saved["verified_at"] == 1000


def test_corrupt_saved_session_is_ignored(monkeypatch, keyring):
    keyring.set_password(auth.SESSION_SERVICE, auth.SESSION_KEY, "{not json")
    assert auth.load_saved() is None


def release(version="9", assets=("CampusGuard-Setup.exe", "checksum.txt")):
    return {"body": version, "assets": [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]}


def test_update_selection():
    assert select_update(release("9"), "5")["url"] == "https://x/CampusGuard-Setup.exe"
    assert select_update(release("5"), "5") is None
    assert select_update(release("9", assets=("CampusGuard.exe", "checksum.txt")), "5") is None


def test_updater_log_never_raises(monkeypatch, tmp_path):
    import campusguard.storage as storage
    from campusguard import updater

    monkeypatch.setattr(storage, "application_data_dir", lambda: tmp_path)
    updater._log("hello")
    assert "hello" in (tmp_path / "updater.log").read_text(encoding="utf-8")
