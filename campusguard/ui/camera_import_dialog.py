"""Import many cameras from a CSV file: pick the file, review every row, then add the ones that are ready."""
from __future__ import annotations

import os
from typing import Iterable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from campusguard.camera_import import MAX_FILE_BYTES, MAX_ROWS, ImportPlan, ImportRow, parse_camera_csv, template_csv
from campusguard.ui.theme import get_palette

INTRO = (
    "Add many cameras in one go from a spreadsheet saved as CSV. Each row is one camera. "
    "Required columns: name, type (RTSP, HTTP, MJPEG, IP or USB) and address. "
    "Optional: port, path, username, password, group (zone), sensitivity, ai."
)
VAULT_NOTE = (
    "Usernames and passwords are saved in the Windows credential vault, never in CampusGuard's database. "
    "The CSV file itself keeps them as plain text, so delete it once the cameras are imported."
)
COLUMNS = ["Line", "Name", "Type", "Address", "Zone", "Result"]
_LINE, _NAME, _TYPE, _ADDRESS, _ZONE, _RESULT = range(6)


class CameraImportDialog(QDialog):
    """Nothing is added here: `rows_to_import` is handed to the main window when the dialog is accepted."""

    def __init__(self, parent: QWidget | None = None, existing: Iterable[tuple[str, str, str]] = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import cameras from CSV")
        self.resize(1040, 600)
        self.setMinimumSize(820, 440)
        self._existing = list(existing)
        self.plan = ImportPlan()
        self.rows_to_import: list[dict] = []

        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        root.addWidget(intro)

        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.choose_button = QPushButton("Choose CSV file…")
        self.choose_button.setProperty("primary", True)
        self.choose_button.clicked.connect(self._choose_file)
        self.template_button = QPushButton("Download template…")
        self.template_button.setToolTip("A CSV with the right columns and a few example rows to copy from")
        self.template_button.clicked.connect(self._save_template)
        self.file_label = QLabel("No file chosen")
        self.file_label.setProperty("muted", True)
        pick.addWidget(self.choose_button)
        pick.addWidget(self.template_button)
        pick.addWidget(self.file_label, 1)
        root.addLayout(pick)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-weight: 600;")
        root.addWidget(self.summary_label)
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setProperty("muted", True)
        self.detail_label.hide()
        root.addWidget(self.detail_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for column, width in ((_LINE, 54), (_NAME, 170), (_TYPE, 70), (_ZONE, 120)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(_ADDRESS, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_RESULT, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        note = QLabel(VAULT_NOTE)
        note.setWordWrap(True)
        note.setProperty("muted", True)
        root.addWidget(note)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.import_button = QPushButton("Import cameras")
        self.import_button.setProperty("primary", True)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.import_button)
        root.addLayout(footer)

    # ---------------------------------------------------------------- loading
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a CSV file of cameras", "", "CSV files (*.csv *.txt);;All files (*)")
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        self.file_label.setText(os.path.basename(path))
        self.file_label.setToolTip(path)
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                raise ValueError("This file is too large to be a list of cameras (over 1 MB). Check that it is the right file.")
            with open(path, "rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except (OSError, ValueError) as error:
            plan = ImportPlan()
            plan.problem = str(error) if isinstance(error, ValueError) else f"The file could not be opened: {error.strerror or error}."
            self.show_plan(plan)
            return
        self.show_plan(parse_camera_csv(data, self._existing))

    def load_text(self, text: str) -> None:
        self.show_plan(parse_camera_csv(text, self._existing))

    def show_plan(self, plan: ImportPlan) -> None:
        self.plan = plan
        self.summary_label.setText(plan.summary())
        details = []
        if plan.ignored_columns and not plan.problem:
            details.append("Columns not used: " + ", ".join(plan.ignored_columns) + ".")
        if plan.rows and plan.with_problems:
            details.append("Rows that need fixing are skipped. Fix them in the file and import again, or add them one by one.")
        self.detail_label.setText(" ".join(details))
        self.detail_label.setVisible(bool(details))
        self._fill(plan.rows)
        ready = plan.ready
        self.import_button.setEnabled(bool(ready))
        self.import_button.setText(f"Import {len(ready)} camera{'s' if len(ready) != 1 else ''}" if ready else "Import cameras")

    def _fill(self, rows: list[ImportRow]) -> None:
        palette = get_palette()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            if row.problems:
                tone = QColor(palette.bad)
            elif row.skip_reason:
                tone = QColor(palette.muted)
            else:
                tone = QColor(palette.good)
            cells = [str(row.line), row.name, row.source_type, row.source_address, row.group_name, row.status]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == _RESULT:
                    item.setForeground(tone)
                elif row.skip_reason and not row.problems:
                    item.setForeground(QColor(palette.muted))
                self.table.setItem(index, column, item)
        self._fit_rows()

    def _fit_rows(self) -> None:
        self.table.resizeRowsToContents()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_rows)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_rows)

    # ---------------------------------------------------------------- template
    def _save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save the CSV template", "campusguard-cameras-template.csv", "CSV files (*.csv)")
        if path:
            self.write_template(path)

    def write_template(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(template_csv())
        except OSError as error:
            self.summary_label.setText(f"The template could not be saved: {error.strerror or error}.")
            return False
        self.summary_label.setText(f"Template saved to {path}. Fill it in, save it as CSV, then choose it here.")
        return True

    # ------------------------------------------------------------------ accept
    def _accept(self) -> None:
        self.rows_to_import = [row.values() for row in self.plan.ready][:MAX_ROWS]
        if self.rows_to_import:
            self.accept()
