"""The app signs in only when BOTH website approvals (login and payment) are granted."""
import pytest

from campusguard import auth


def _status(monkeypatch, body, code=200):
    monkeypatch.setattr(auth, "_request", lambda *a, **k: (code, body))


def test_both_approved_passes(monkeypatch):
    _status(monkeypatch, {"status": "approved", "login_status": "approved", "payment_status": "approved", "access_granted": True})
    auth.check_access("t")


@pytest.mark.parametrize("body,fragment,kind", [
    ({"status": "pending", "login_status": "approved", "payment_status": "pending", "access_granted": False}, "Waiting for: payment", "pending"),
    ({"status": "pending", "login_status": "pending", "payment_status": "approved", "access_granted": False}, "Waiting for: login", "pending"),
    ({"status": "pending", "login_status": "pending", "payment_status": "pending"}, "login and payment", "pending"),
    ({"status": "approved", "login_status": "approved", "payment_status": "pending", "access_granted": False}, "payment", "pending"),
    ({"status": "rejected", "login_status": "rejected", "payment_status": "pending"}, "login approval was not granted", "rejected"),
    ({"status": "rejected", "login_status": "approved", "payment_status": "rejected"}, "payment approval was not granted", "rejected"),
])
def test_one_missing_approval_blocks_the_app(monkeypatch, body, fragment, kind):
    _status(monkeypatch, body)
    with pytest.raises(auth.AuthError) as error:
        auth.check_access("t")
    assert fragment in str(error.value) and error.value.kind == kind


def test_older_server_reply_without_the_new_fields_still_works(monkeypatch):
    _status(monkeypatch, {"status": "approved"})
    auth.check_access("t")
