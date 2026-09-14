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

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import _torchaudio_patch
from ..settings import CONFIG_DIR

GPU_ENV_DIR = CONFIG_DIR / "gpu-venv"
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu121"

ProgressCallback = Callable[[str], None]


class SystemPythonNotFoundError(RuntimeError):
    pass


def _is_store_alias(path: str) -> bool:
    return "windowsapps" in path.lower()


def find_system_python() -> str | None:
    """Busca un Python normal instalado en el sistema (no el .exe empaquetado).

    Descarta a propósito el alias de Microsoft Store (WindowsApps\\python.exe):
    incluso con el PATH limpio (ver _subprocess_env), crear un venv con ese Python
    desde un subproceso lanzado por nuestro .exe empaquetado sigue produciendo un
    entorno incompleto (sin pyvenv.cfg) — parece ser una limitación propia del
    alias, no de nuestro entorno. Mejor fallar rápido con un mensaje claro que
    intentarlo y terminar en un error confuso a mitad de camino.

    En Windows, WindowsApps suele estar ANTES en el PATH que una instalación real de
    python.org, así que `shutil.which` (que devuelve el primer match) puede tapar un
    Python perfectamente válido. Por eso acá se recorre TODO el PATH, no solo el
    primer resultado, y como último recurso se buscan ubicaciones típicas de
    instalación de python.org.
    """
    exe_names = ("python.exe", "python3.exe") if sys.platform == "win32" else ("python3", "python")

    for name in exe_names:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            candidate = Path(directory) / name
            if candidate.is_file() and not _is_store_alias(str(candidate)):
                return str(candidate)

    py_launcher = shutil.which("py")
    if py_launcher and not _is_store_alias(py_launcher):
        try:
            result = subprocess.run(
                [py_launcher, "-3", "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            candidate = result.stdout.strip()
            if result.returncode == 0 and candidate and not _is_store_alias(candidate) and Path(candidate).is_file():
                return candidate
        except (OSError, subprocess.SubprocessError):
            pass

    if sys.platform == "win32":
        search_roots = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path("C:/Program Files"),
        ]
        for root in search_roots:
            if not root.is_dir():
                continue
            for entry in sorted(root.glob("Python3*"), reverse=True):
                candidate = entry / "python.exe"
                if candidate.is_file():
                    return str(candidate)

    return None


def gpu_python_path() -> Path:
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    exe_name = "python.exe" if sys.platform == "win32" else "python"
    return GPU_ENV_DIR / bin_dir / exe_name


def is_installed() -> bool:
    """True solo si hay un venv completo (no a medio crear/corrupto)."""
    return gpu_python_path().is_file() and (GPU_ENV_DIR / "pyvenv.cfg").is_file()


def _subprocess_env() -> dict[str, str]:
    """PATH sin la carpeta del propio .exe empaquetado.

    Dentro de un .exe de PyInstaller, PATH trae antepuesta la carpeta del programa
    (para que el bootloader encuentre sus propias DLLs). Un subproceso hereda ese
    PATH, así que un Python externo lanzado desde acá podría terminar cargando por
    error una DLL de Python empaquetada junto a la app (de otra versión/build) en vez
    de la suya — eso puede corromper silenciosamente cosas como la creación de un
    venv (por ejemplo, queda sin pyvenv.cfg aunque el comando no reporte error).
    """
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        internal_dir = app_dir / "_internal"
        parts = env.get("PATH", "").split(os.pathsep)
        parts = [
            p
            for p in parts
            if p and Path(p).resolve() not in (app_dir, internal_dir)
        ]
        env["PATH"] = os.pathsep.join(parts)
    return env


def _stream_subprocess(cmd: list[str], progress_callback: ProgressCallback | None) -> None:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_subprocess_env(),
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
            "No se encontró un Python de python.org instalado en el sistema (el de "
            "Microsoft Store no sirve para esto: no logra crear el entorno correctamente "
            "desde acá). Instala Python 3.10+ desde python.org marcando \"Add to PATH\" "
            "durante la instalación, y volvé a intentar."
        )

    def report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    if GPU_ENV_DIR.exists() and not (GPU_ENV_DIR / "pyvenv.cfg").is_file():
        report("Se encontró un entorno anterior incompleto; lo vuelvo a crear...")
        shutil.rmtree(GPU_ENV_DIR)

    GPU_ENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    if not GPU_ENV_DIR.exists():
        report(f"Creando entorno en {GPU_ENV_DIR} con {system_python}...")
        _stream_subprocess([system_python, "-m", "venv", str(GPU_ENV_DIR)], progress_callback)

    if not (GPU_ENV_DIR / "pyvenv.cfg").is_file() or not gpu_python_path().is_file():
        raise RuntimeError(
            f"La creación del entorno falló: {GPU_ENV_DIR} quedó incompleta. Puede que "
            f"\"{system_python}\" no sea un Python válido para crear entornos virtuales. "
            "Instala Python desde python.org (no la versión de Microsoft Store) y "
            "volvé a intentar."
        )

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
    _stream_subprocess(
        [venv_python, "-m", "pip", "install", "demucs", "soundfile"], progress_callback
    )

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

    demucs_opts = ["-n", model, "-d", "cuda", "-o", str(stems_dir), str(source_audio)]
    # Corre como script inline (en vez de `-m demucs`) para poder aplicar el mismo
    # parche de guardado con soundfile dentro del venv externo: ese proceso es un
    # Python aparte, sin acceso a nuestro paquete, así que el parche viaja como texto.
    script = _torchaudio_patch.SOURCE + (
        f"\nfrom demucs.separate import main\nmain({demucs_opts!r})\n"
    )
    cmd = [str(gpu_python_path()), "-c", script]
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
