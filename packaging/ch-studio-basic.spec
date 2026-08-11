# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para CH Studio Basic (solo descarga de YouTube).

Uso (desde la raíz del repo, con el venv activado):
    pyinstaller packaging/ch-studio-basic.spec

El .exe queda en dist/ch-studio-basic/ch-studio-basic.exe.

A propósito NO incluye librosa/Demucs/torch: el entry point (main_basic.py) nunca
importa chstudio.core.chart/autochart/stems, así que el análisis de dependencias de
PyInstaller ni los toca. Resultado: un ejecutable mucho más liviano que el completo.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

hidden_imports = collect_submodules("yt_dlp")

datas = []
tools_dir = ROOT / "tools"
if tools_dir.exists():
    datas.append((str(tools_dir), "tools"))

a = Analysis(
    [str(SRC / "chstudio" / "main_basic.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["chstudio.core.chart", "chstudio.core.autochart", "chstudio.core.stems"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KYTDownloader-Basic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="KYTDownloader-Basic",
)
