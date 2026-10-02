import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setApplicationName("CampusGuard")
window = MainWindow()
window.show()
sys.exit(app.exec())
