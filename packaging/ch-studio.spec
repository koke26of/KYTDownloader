# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para CH Studio.

Uso (desde la raíz del repo, con el venv activado y `pip install -e ".[dev]"`):
    pyinstaller packaging/ch-studio.spec

El .exe queda en dist/ch-studio/ch-studio.exe.

Nota: si Demucs/torch están instalados en el venv, PyInstaller los incluirá y el
bundle será mucho más pesado. Para un build liviano (solo descarga + prep. Moises +
organizador CH), usa un venv sin el extra [stems].
"""
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller ejecuta el .spec con exec(), inyectando SPECPATH (carpeta que contiene
# este archivo) en el namespace en vez de definir __file__.
ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

hidden_imports = (
    collect_submodules("yt_dlp")
    + collect_submodules("librosa")
    + ["soundfile"]
)

datas = collect_data_files("librosa")

# Demucs/torch son opcionales ([stems] extra). Si están instalados en el venv que
# corre PyInstaller, los incluimos automáticamente (bundle mucho más pesado, ~varios GB).
if importlib.util.find_spec("demucs") is not None:
    hidden_imports += collect_submodules("demucs") + collect_submodules("torch") + collect_submodules("torchaudio")
    datas += collect_data_files("demucs")

# Empaqueta tools/ (ffmpeg.exe embebido, si el usuario lo colocó ahí) junto al .exe.
tools_dir = ROOT / "tools"
if tools_dir.exists():
    datas.append((str(tools_dir), "tools"))

a = Analysis(
    [str(SRC / "chstudio" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KYTDownloader",
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
    name="KYTDownloader",
)
