# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Scan this computer's network for cameras and add one after it has been tested."""
from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from campusguard import camera_discovery
from campusguard.camera_discovery import COMMON_STREAM_PATHS, FoundCamera
from campusguard.settings import CameraCredentials
from campusguard.sources import build_rtsp_url
from campusguard.ui.workers import Worker

PERMISSION_NOTE = (
    "Only scan networks you have permission to scan, such as your school's own. "
    "The scan looks for ONVIF cameras and for open camera ports (554 and 8554) on the network "
    "this computer is connected to. It cannot see other networks, and some networks block "
    "discovery. If nothing is found, you can still add a camera by typing its address."
)

COLUMNS = ["Address", "Found by", "Username", "Password", "Stream path", "Status", "", ""]
_ADDRESS, _FOUND_BY, _USER, _PASSWORD, _PATH, _STATUS, _TEST, _ADD = range(8)

# Threads and tests that outlive a closed dialog stay referenced here until they finish.
_ACTIVE: set[QThread] = set()


def _scan(cancel: threading.Event, progress: Callable[[int, int], None]) -> list[FoundCamera]:
    return camera_discovery.scan_network(cancel=cancel, progress=progress)


def _probe(source_type: str, address: str, credentials: CameraCredentials) -> tuple[bool, str]:
    # camera_runtime pulls in OpenCV/PyTorch, so it is imported only when a test is run.
    from campusguard.camera_runtime import probe_source

    return probe_source(source_type, address, credentials)


def _set_tone(label: QLabel, tone: str | None) -> None:
    label.setProperty("tone", tone)
    label.setProperty("muted", tone is None)
    label.style().unpolish(label)
    label.style().polish(label)


class CameraScanThread(QThread):
    progress = Signal(int, int)
    found = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            cameras = _scan(self.cancel_event, lambda done, total: self.progress.emit(done, total))
        except Exception as error:
            self.failed.emit(str(error) or "The scan could not run on this network.")
            return
        self.found.emit(cameras)


class _Row:
    def __init__(self, camera: FoundCamera) -> None:
        self.camera = camera
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.path = QComboBox()
        self.path.setEditable(True)
        self.path.addItems(list(COMMON_STREAM_PATHS))
        self.status = QLabel("Not tested")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        self.test_button = QPushButton("Test")
        self.add_button = QPushButton("Add")
        self.add_button.setProperty("primary", True)
        self.add_button.setEnabled(False)
        self.message = ""
        self.tested_ok = False
        self.busy = False


class CameraScanDialog(QDialog):
    """Lists cameras found on the local network. Each one must pass Test before it can be added."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scan network for cameras")
        self.resize(1100, 540)
        self.setMinimumSize(900, 420)
        self.selected: dict[str, object] | None = None
        self._rows: list[_Row] = []
        self._thread: CameraScanThread | None = None
        self._closing = False

        root = QVBoxLayout(self)
        root.setSpacing(10)

        note = QLabel(PERMISSION_NOTE)
        note.setWordWrap(True)
        note.setProperty("muted", True)
        root.addWidget(note)

        self._network = camera_discovery.local_network()
        local = camera_discovery.local_address()
        if self._network is not None:
            network_text = f"Network to scan: {self._network} (this computer is {local})"
        else:
            network_text = (
                "This computer is not on a private network, so there is nothing safe to scan. "
                "Add the camera by typing its address instead."
            )
        self.network_label = QLabel(network_text)
        self.network_label.setWordWrap(True)
        root.addWidget(self.network_label)

        controls = QHBoxLayout()
        self.scan_button = QPushButton("Scan network")
        self.scan_button.setProperty("primary", True)
        self.scan_button.setEnabled(self._network is not None)
        self.scan_button.clicked.connect(self._toggle_scan)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.scan_status = QLabel("")
        self.scan_status.setProperty("muted", True)
        self.scan_status.setWordWrap(True)
        controls.addWidget(self.scan_button)
        controls.addWidget(self.progress, 1)
        root.addLayout(controls)
        root.addWidget(self.scan_status)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for column, width in ((_ADDRESS, 112), (_FOUND_BY, 150), (_USER, 124), (_PASSWORD, 124), (_TEST, 86), (_ADD, 86)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(_PATH, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_STATUS, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("")
        self.empty_label.setWordWrap(True)
        self.empty_label.setProperty("muted", True)
        self.empty_label.hide()
        root.addWidget(self.empty_label)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

    # ------------------------------------------------------------------ scanning
    def _toggle_scan(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancel()
            self.scan_status.setText("Stopping…")
            self.scan_button.setEnabled(False)
            return
        self.start_scan()

    def start_scan(self) -> None:
        if self._network is None:
            return
        self._clear_rows()
        self.empty_label.hide()
        self.progress.setRange(0, 0)  # busy while the ONVIF probe waits for answers
        self.scan_button.setText("Stop")
        self.scan_status.setText("Scanning… this usually takes under a minute.")
        thread = CameraScanThread()
        thread.progress.connect(self._on_progress)
        thread.found.connect(self._on_found)
        thread.failed.connect(self._on_failed)
        thread.finished.connect(lambda t=thread: _ACTIVE.discard(t))  # no widgets touched here
        thread.finished.connect(self._scan_finished)
        self._thread = thread
        _ACTIVE.add(thread)
        thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        if self._closing:
            return
        if self.progress.maximum() != total:
            self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)

    def _on_found(self, cameras: object) -> None:
        if self._closing:
            return
        cancelled = bool(self._thread and self._thread.cancel_event.is_set())
        self.progress.setRange(0, 1)
        self.progress.setValue(0 if cancelled else 1)
        for camera in cameras:  # type: ignore[union-attr]
            self._add_row(camera)
        count = len(self._rows)
        prefix = "Stopped. " if cancelled else ""
        if count:
            self.scan_status.setText(
                f"{prefix}Found {count} possible camera{'s' if count != 1 else ''}. "
                "Enter each camera's username and password, press Test, then Add."
            )
        else:
            self.scan_status.setText(f"{prefix}No cameras found.")
            self.empty_label.setText(
                "Nothing answered on this network. The network may block discovery, or the camera "
                "may be on a different network. You can close this window and type the address instead."
            )
            self.empty_label.show()

    def _on_failed(self, message: str) -> None:
        if self._closing:
            return
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.scan_status.setText(f"Scan failed: {message}")

    def _scan_finished(self) -> None:
        if self._closing:
            return
        self.scan_button.setText("Scan network")
        self.scan_button.setEnabled(self._network is not None)

    # ------------------------------------------------------------------ results table
    def _clear_rows(self) -> None:
        self._rows.clear()
        self.table.setRowCount(0)

    def _add_row(self, camera: FoundCamera) -> None:
        row = _Row(camera)
        index = self.table.rowCount()
        self.table.insertRow(index)
        self.table.setItem(index, _ADDRESS, QTableWidgetItem(camera.host))
        self.table.setItem(index, _FOUND_BY, QTableWidgetItem(camera.found_by))
        self.table.setCellWidget(index, _USER, row.username)
        self.table.setCellWidget(index, _PASSWORD, row.password)
        self.table.setCellWidget(index, _PATH, row.path)
        self.table.setCellWidget(index, _STATUS, row.status)
        self.table.setCellWidget(index, _TEST, row.test_button)
        self.table.setCellWidget(index, _ADD, row.add_button)
        row.username.setPlaceholderText("Username")
        row.password.setPlaceholderText("Password")
        row.username.setAccessibleName(f"Username for {camera.host}")
        row.password.setAccessibleName(f"Password for {camera.host}")
        for edited in (row.username.textChanged, row.password.textChanged, row.path.editTextChanged):
            edited.connect(lambda _text, r=row: self._invalidate(r))
        row.test_button.clicked.connect(lambda _checked=False, r=row: self.test_row(r))
        row.add_button.clicked.connect(lambda _checked=False, r=row: self.add_row(r))
        self._rows.append(row)

    def _invalidate(self, row: _Row) -> None:
        """A changed username, password or path means the earlier test no longer applies."""
        if row.busy or not row.tested_ok:
            return
        row.tested_ok = False
        row.add_button.setEnabled(False)
        row.status.setText("Not tested")
        _set_tone(row.status, None)

    def _url_for(self, row: _Row) -> str:
        return build_rtsp_url(row.camera.host, row.camera.port, "", "", row.path.currentText())

    def test_row(self, row: _Row) -> None:
        if row.busy:
            return
        try:
            url = self._url_for(row)
        except ValueError as error:
            row.status.setText(str(error))
            _set_tone(row.status, "bad")
            return
        credentials = CameraCredentials(row.username.text(), row.password.text())
        row.busy = True
        row.tested_ok = False
        row.add_button.setEnabled(False)
        row.test_button.setEnabled(False)
        row.status.setText("Testing…")
        _set_tone(row.status, None)
        row_id = id(row)

        def run() -> tuple[int, bool, str]:
            try:
                ok, message = _probe("RTSP", url, credentials)
            except Exception:
                ok, message = False, "The test could not run."
            return row_id, ok, message

        worker = Worker(run)
        _ACTIVE.add(worker)
        worker.finished.connect(lambda w=worker: _ACTIVE.discard(w))  # no widgets touched here
        worker.succeeded.connect(self._test_done)
        worker.start()

    def _test_done(self, result: object) -> None:
        row_id, ok, message = result  # type: ignore[misc]
        row = next((r for r in self._rows if id(r) == row_id), None)
        if row is None:  # a rescan replaced the table while this test was running
            return
        row.busy = False
        if self._closing:
            return
        row.tested_ok = bool(ok)
        row.message = str(message)
        row.status.setText(row.message)
        _set_tone(row.status, "good" if ok else "bad")
        row.test_button.setEnabled(True)
        row.add_button.setEnabled(bool(ok))

    def add_row(self, row: _Row) -> None:
        if not row.tested_ok:
            return
        self.selected = {
            "host": row.camera.host,
            "port": row.camera.port,
            "path": row.path.currentText().strip() or "/",
            "username": row.username.text(),
            "password": row.password.text(),
            "message": row.message,
        }
        self.accept()

    # ------------------------------------------------------------------ closing
    def done(self, result: int) -> None:
        self._closing = True
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait(3000)
        super().done(result)
