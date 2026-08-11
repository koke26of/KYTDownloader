"""Punto de entrada de CH Studio."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from chstudio.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CH Studio")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
