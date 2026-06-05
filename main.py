"""Entry point for the S4P Network Analyzer application."""

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

# Ensure the app module is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("高速线网分析仪")
    app.setOrganizationName("NEXT Analyzer")

    # Set font for better readability on Windows
    font = app.font()
    font.setPointSize(9)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
