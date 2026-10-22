from __future__ import annotations

import json

import keyring

from campusguard.settings import CameraCredentials


class CredentialVault:
    """Stores camera credentials in the operating system's credential vault."""

    SERVICE_NAME = "CampusGuard camera sources"
    USERNAME_KEY = "credential-pair"
    SERVER_TOKEN_SERVICE = "CampusGuard remote server"
    SERVER_TOKEN_KEY = "access-token"

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

    def save_server_token(self, token: str) -> None:
        """Store the remote server token separately from camera credentials."""
        if token:
            keyring.set_password(self.SERVER_TOKEN_SERVICE, self.SERVER_TOKEN_KEY, token)
        else:
            self.delete_server_token()

    def load_server_token(self) -> str:
        return keyring.get_password(self.SERVER_TOKEN_SERVICE, self.SERVER_TOKEN_KEY) or ""

    def delete_server_token(self) -> None:
        try:
            keyring.delete_password(self.SERVER_TOKEN_SERVICE, self.SERVER_TOKEN_KEY)
        except keyring.errors.PasswordDeleteError:
            pass

    def delete(self, camera_id: str) -> None:
        try:
            keyring.delete_password(self.SERVICE_NAME, camera_id)
        except keyring.errors.PasswordDeleteError:
            pass