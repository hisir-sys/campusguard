"""Supervisor PIN: a second person's approval before evidence is destroyed.

Only a salted scrypt hash is stored (in the OS credential vault). This is an
approval step inside the app, not encryption: protect the disk with BitLocker.
"""

from __future__ import annotations

import hashlib
import hmac
import os

MIN_LENGTH = 4


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = hashlib.scrypt(pin.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def valid_new_pin(pin: str) -> bool:
    return len(pin.strip()) >= MIN_LENGTH
