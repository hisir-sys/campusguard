import io
import json
import urllib.error

import pytest

from campusguard import profile


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_save_sends_trimmed_numbers_and_returns_the_server_copy(monkeypatch):
    seen = {}
    monkeypatch.setattr(profile.auth, "fresh_access_token", lambda: "tok")

    def fake_open(request, timeout):
        seen["method"] = request.get_method()
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        return _Response(json.dumps({"email": "a@b.c", "full_name": "Asha"}).encode())

    monkeypatch.setattr(profile.urllib.request, "urlopen", fake_open)
    result = profile.save_profile("Asha", "BDMI", "+91 70000 00000", [" +917003276998 ", "", "  "] + ["1" * 10] * 8)
    assert result["full_name"] == "Asha"
    assert seen["method"] == "PUT" and seen["auth"] == "Bearer tok"
    assert seen["body"]["alert_phones"][0] == "+917003276998"
    assert len(seen["body"]["alert_phones"]) == profile.MAX_ALERT_NUMBERS


def test_signed_out_is_a_friendly_error(monkeypatch):
    monkeypatch.setattr(profile.auth, "fresh_access_token", lambda: "")
    with pytest.raises(profile.ProfileError):
        profile.fetch_profile()


def test_server_message_is_passed_on(monkeypatch):
    monkeypatch.setattr(profile.auth, "fresh_access_token", lambda: "tok")

    def fake_open(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b'{"error": "Enter a phone number with 8 to 15 digits."}'))

    monkeypatch.setattr(profile.urllib.request, "urlopen", fake_open)
    with pytest.raises(profile.ProfileError, match="8 to 15 digits"):
        profile.save_profile("A", "B", "123", [])
