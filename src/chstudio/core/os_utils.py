"""Utilidades de sistema operativo sin dependencias pesadas.

Vive aparte de stems.py a propósito: PyInstaller bundlea cualquier import que
encuentre en un archivo (incluso dentro de funciones nunca llamadas), así que si el
build básico importara stems.py arrastraría Demucs/PyTorch aunque nunca los use.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(["explorer", str(path)])
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])
