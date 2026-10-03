from __future__ import annotations

import json

import keyring

from campusguard.settings import CameraCredentials


class CredentialVault:
    """Stores camera credentials in the operating system's credential vault."""

    SERVICE_NAME = "CampusGuard camera sources"
    USERNAME_KEY = "credential-pair"

    def save(self, camera_id: str, credentials: CameraCredentials) -> None:
        if not credentials.username and not credentials.password:
            return
        payload = json.dumps(
            {"username": credentials.username, "password": credentials.password}
        )
        keyring.set_password(self.SERVICE_NAME, camera_id, payload)

    def load(self, camera_id: str) -> CameraCredentials:
        payload = keyring.get_password(self.SERVICE_NAME, camera_id)
        if not payload:
            return CameraCredentials()
        values = json.loads(payload)
        return CameraCredentials(
            username=str(values.get("username", "")),
            password=str(values.get("password", "")),
        )

    def delete(self, camera_id: str) -> None:
        try:
            keyring.delete_password(self.SERVICE_NAME, camera_id)
        except keyring.errors.PasswordDeleteError:
            pass