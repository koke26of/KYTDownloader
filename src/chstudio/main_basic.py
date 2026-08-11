"""Punto de entrada de KYTDownloader Basic (nombre provisorio; solo descarga de YouTube)."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from chstudio.ui.basic_window import BasicMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KYTDownloader Basic")
    window = BasicMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
