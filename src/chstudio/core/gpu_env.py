"""Aceleración GPU opcional para Demucs, instalada bajo demanda.

La app se distribuye con Demucs en modo CPU (liviano). PyTorch con CUDA pesa varios
GB, así que en vez de empaquetarlo, este módulo crea un entorno Python APARTE (fuera
del .exe, con `python -m venv`) e instala ahí torch+CUDA+demucs cuando el usuario lo
pide. La separación de stems corre entonces como subproceso de ESE python externo —
a diferencia del bug que tuvimos antes con `sys.executable` (que dentro de un .exe
empaquetado apunta al propio ejecutable), acá el target es un intérprete de Python
real, así que subprocess es la forma correcta de invocarlo.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ..settings import CONFIG_DIR

GPU_ENV_DIR = CONFIG_DIR / "gpu-venv"
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu121"

ProgressCallback = Callable[[str], None]


class SystemPythonNotFoundError(RuntimeError):
    pass


def find_system_python() -> str | None:
    """Busca un Python normal instalado en el sistema (no el .exe empaquetado)."""
    for candidate in ("python", "python3"):
        found = shutil.which(candidate)
        if found:
            return found
    py_launcher = shutil.which("py")
    if py_launcher:
        return py_launcher
    return None


def gpu_python_path() -> Path:
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    exe_name = "python.exe" if sys.platform == "win32" else "python"
    return GPU_ENV_DIR / bin_dir / exe_name


def is_installed() -> bool:
    return gpu_python_path().is_file()


def _stream_subprocess(cmd: list[str], progress_callback: ProgressCallback | None) -> None:
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert process.stdout is not None
    for line in process.stdout:
        if progress_callback and line.strip():
            progress_callback(line.rstrip())
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"Comando falló (código {returncode}): {' '.join(cmd)}")


def install_gpu_env(progress_callback: ProgressCallback | None = None) -> None:
    """Crea el venv externo e instala torch+CUDA y demucs ahí. Tarda varios minutos
    (descarga ~2.5GB) y requiere que el usuario tenga Python instalado en el sistema.
    """
    system_python = find_system_python()
    if not system_python:
        raise SystemPythonNotFoundError(
            "No se encontró un Python instalado en el sistema. Instala Python 3.10+ "
            "desde python.org (marcando \"Add to PATH\") y volvé a intentar."
        )

    def report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    GPU_ENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    if not GPU_ENV_DIR.exists():
        report(f"Creando entorno en {GPU_ENV_DIR} con {system_python}...")
        _stream_subprocess([system_python, "-m", "venv", str(GPU_ENV_DIR)], progress_callback)

    venv_python = str(gpu_python_path())

    report("Actualizando pip...")
    _stream_subprocess([venv_python, "-m", "pip", "install", "--upgrade", "pip"], progress_callback)

    report("Instalando PyTorch con soporte CUDA (descarga grande, puede tardar varios minutos)...")
    _stream_subprocess(
        [
            venv_python,
            "-m",
            "pip",
            "install",
            "torch",
            "torchaudio",
            "--index-url",
            CUDA_INDEX_URL,
        ],
        progress_callback,
    )

    report("Instalando Demucs...")
    _stream_subprocess([venv_python, "-m", "pip", "install", "demucs"], progress_callback)

    report("Listo. La separación local usará la GPU automáticamente de ahora en más.")


def uninstall_gpu_env() -> None:
    if GPU_ENV_DIR.exists():
        shutil.rmtree(GPU_ENV_DIR)


def separate(
    source_audio: Path,
    song_dir: Path,
    model: str = "htdemucs",
    progress_callback: ProgressCallback | None = None,
) -> tuple[Path, dict[str, Path]]:
    """Separa stems corriendo Demucs en el venv externo con GPU. Devuelve
    (result_dir, {nombre_stem: Path}), igual que stems.separate_local."""
    if not is_installed():
        raise RuntimeError("El entorno GPU no está instalado todavía.")

    stems_dir = song_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(gpu_python_path()),
        "-m",
        "demucs",
        "-n",
        model,
        "-d",
        "cuda",
        "-o",
        str(stems_dir),
        str(source_audio),
    ]
    _stream_subprocess(cmd, progress_callback)

    track_name = source_audio.stem
    result_dir = stems_dir / model / track_name
    stem_files: dict[str, Path] = {}
    for name in ("vocals", "drums", "bass", "other"):
        candidate = result_dir / f"{name}.wav"
        if candidate.exists():
            stem_files[name] = candidate

    if not stem_files:
        raise RuntimeError(f"Demucs (GPU) no generó stems en la ruta esperada: {result_dir}")

    return result_dir, stem_files
