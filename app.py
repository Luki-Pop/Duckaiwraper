import os
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

import sys
from PyQt6 import QtWidgets, QtCore, QtWebEngineWidgets, QtGui

URL = "https://duck.ai"

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Duck.ai")
        self.resize(1200, 800)
        web = QtWebEngineWidgets.QWebEngineView()
        web.setUrl(QtCore.QUrl(URL))
        self.setCentralWidget(web)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
