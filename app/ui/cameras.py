import cv2
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

class CamerasPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.views = {}
        self.names = {}

        layout = QVBoxLayout(self)

        title = QLabel("Camera Network")
        title.setStyleSheet("font-size:28px;font-weight:800;")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setPlaceholderText("0 or C:\\Videos\\campus.mp4")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Camera name")

        add = QPushButton("Add Camera")
        add.clicked.connect(self.add)

        webcam = QPushButton("Webcam 0")
        webcam.clicked.connect(
            lambda: self.quick_add("0", "Webcam 0")
        )

        row.addWidget(self.source, 2)
        row.addWidget(self.name)
        row.addWidget(add)
        row.addWidget(webcam)
        layout.addLayout(row)

        self.feed_layout = QVBoxLayout()
        layout.addLayout(self.feed_layout)

    def quick_add(self, source, name):
        self.source.setText(source)
        self.name.setText(name)
        self.add()

    def add(self):
        source = self.source.text().strip()
        name = self.name.text().strip() or f"Camera {len(self.views)+1}"

        if not source:
            QMessageBox.warning(
                self, "Camera", "Enter a webcam index or video path."
            )
            return

        camera_id = f"camera_{len(self.views)+1}"

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#071019;border:1px solid #1a3040;border-radius:12px;}"
        )
        box = QVBoxLayout(frame)
        box.addWidget(QLabel(name + "  •  LIVE"))

        view = QLabel("Connecting...")
        view.setMinimumHeight(280)
        view.setAlignment(Qt.AlignCenter)
        box.addWidget(view)

        self.feed_layout.addWidget(frame)
        self.views[camera_id] = view
        self.names[camera_id] = name

        self.main.cameras.add(camera_id, source)
        self.source.clear()
        self.name.clear()

    def on_frame(self, camera_id, frame):
        if camera_id not in self.views:
            return

        annotated, detections = self.main.detector.process(frame)

        if detections and self.main.detector.can_alert(
            self.main.settings["alert_cooldown"]
        ):
            for detection in detections[:2]:
                self.main.add_incident(
                    self.names[camera_id], detection
                )

        rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape

        image = QImage(
            rgb.data, width, height, channels * width,
            QImage.Format_RGB888
        )

        self.views[camera_id].setPixmap(
            QPixmap.fromImage(image).scaled(
                self.views[camera_id].size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def on_error(self, camera_id, message):
        if camera_id in self.views:
            self.views[camera_id].setText("ERROR: " + message)
