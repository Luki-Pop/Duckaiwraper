import sys
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from main_window import MainWindow

if __name__ == "__main__":
    # Required before QApplication on some systems
    QtWidgets.QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("DuckAI Wrapper")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())