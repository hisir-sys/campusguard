"""Small local status window for a headless CampusGuard server."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from campusguard.server.client import RemoteServerClient
from campusguard.server.config import ServerConfig
from campusguard.storage import application_data_dir


class _StatusPoll(QThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, client: RemoteServerClient, log_path: Path):
        super().__init__()
        self.client = client
        self.log_path = log_path

    def run(self):
        try:
            status = self.client.test_connection()
            last_error = "No recent server errors."
            try:
                lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
                matches = [line for line in lines if " ERROR " in line or " WARNING " in line]
                if matches:
                    last_error = matches[-1][-300:]
            except OSError:
                pass
            self.result_ready.emit({"status": status, "last_error": last_error})
        except Exception as error:
            self.failed.emit(str(error))


class ServerStatusWindow(QWidget):
    def __init__(self, config: ServerConfig, token: str):
        super().__init__()
        self.config = config
        self.token = token
        self._worker: _StatusPoll | None = None
        self.setWindowTitle("CampusGuard Server Status")
        self.setMinimumSize(460, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        title = QLabel("CampusGuard Server")
        title.setStyleSheet("font-size: 18px; font-weight: 800;")
        layout.addWidget(title)
        self.state = QLabel("Checking the local server…")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.counts = QLabel("Camera health: waiting for server response")
        self.counts.setWordWrap(True)
        layout.addWidget(self.counts)
        self.last_error = QLabel("Last error: checking logs…")
        self.last_error.setWordWrap(True)
        self.last_error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.last_error, 1)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh now")
        self.refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        scheme = "https" if self.config.tls_cert_file and self.config.tls_key_file else "http"
        client = RemoteServerClient(f"{scheme}://127.0.0.1:{self.config.port}", self.token, timeout=1.5, retries=0)
        log_path = application_data_dir() / "logs" / "server.log"
        worker = _StatusPoll(client, log_path)
        self._worker = worker
        worker.result_ready.connect(self._on_result)
        worker.failed.connect(self._on_error)
        worker.finished.connect(self._on_finished)
        self.refresh_button.setEnabled(False)
        worker.start()

    def _on_result(self, result):
        data = result["status"]
        counts = data.get("cameras", {})
        self.state.setText(f"Running · {data.get('version', 'CampusGuard')} · uptime {data.get('uptime_seconds', 0)} seconds")
        self.counts.setText(
            f"Cameras: {counts.get('total', 0)} total · {counts.get('ok', 0)} ok · "
            f"{counts.get('stalled', 0)} stalled · {counts.get('offline', 0)} offline · "
            f"{counts.get('connecting', 0)} connecting"
        )
        self.last_error.setText(f"Last error: {result['last_error']}")

    def _on_error(self, message: str):
        self.state.setText(f"Server is not reachable: {message}")
        self.counts.setText("Camera health is unavailable until the server responds.")
        self.last_error.setText("Last error: check the server.log file in the CampusGuard app-data folder.")

    def _on_finished(self):
        worker, self._worker = self._worker, None
        self.refresh_button.setEnabled(True)
        if worker is not None:
            worker.deleteLater()

    def closeEvent(self, event):
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(3000)
        event.accept()
