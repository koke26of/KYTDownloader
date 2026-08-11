"""Separación de stems: preparación para Moises.ai y separación local con Demucs."""
from __future__ import annotations

import shutil
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import ffmpeg_utils
from .os_utils import open_folder  # re-exportado: los callers existentes usan stems.open_folder

MOISES_URL = "https://moises.ai/"

ProgressCallback = Callable[[str], None]


class DemucsNotInstalledError(RuntimeError):
    pass


@dataclass
class StemsResult:
    stems_dir: Path
    stem_files: dict[str, Path]  # {"vocals": Path, "drums": Path, "bass": Path, "other": Path}


def prepare_for_moises(
    source_audio: Path,
    song_dir: Path,
    ffmpeg_path: str = "",
    audio_format: str = "wav",
) -> Path:
    """Deja una copia limpia del audio en song_dir/stems_input/ lista para subir a Moises.

    Devuelve la ruta al archivo preparado.
    """
    input_dir = song_dir / "stems_input"
    input_dir.mkdir(parents=True, exist_ok=True)
    dest = input_dir / f"input.{audio_format}"

    if source_audio.suffix.lstrip(".").lower() == audio_format:
        shutil.copyfile(source_audio, dest)
    else:
        extra_args = ["-vn"]
        if audio_format == "wav":
            extra_args += ["-c:a", "pcm_s16le", "-ar", "44100"]
        elif audio_format == "mp3":
            extra_args += ["-c:a", "libmp3lame", "-q:a", "2"]
        ffmpeg_utils.convert_audio(source_audio, dest, ffmpeg_path, extra_args=extra_args)

    return dest


def open_moises_website() -> None:
    webbrowser.open(MOISES_URL)


def is_demucs_available() -> bool:
    try:
        import demucs  # noqa: F401

        return True
    except ImportError:
        return False


def detect_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class _ProgressStream:
    """Captura texto escrito por Demucs (prints y barras tqdm) y lo reenvía línea a línea."""

    def __init__(self, callback: ProgressCallback | None) -> None:
        self._callback = callback
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while True:
            cut = min(
                (i for i in (self._buffer.find("\n"), self._buffer.find("\r")) if i != -1),
                default=-1,
            )
            if cut == -1:
                break
            line, self._buffer = self._buffer[:cut], self._buffer[cut + 1 :]
            if line.strip() and self._callback:
                self._callback(line.strip())
        return len(text)

    def flush(self) -> None:
        pass


def separate_local(
    source_audio: Path,
    song_dir: Path,
    model: str = "htdemucs",
    device: str = "auto",
    progress_callback: ProgressCallback | None = None,
) -> StemsResult:
    """Separa stems localmente con Demucs. Requiere el extra opcional [stems] instalado.

    Llama a la API de Demucs directamente en el mismo proceso (en vez de lanzar
    `sys.executable -m demucs` como subproceso): dentro de un .exe empaquetado con
    PyInstaller, sys.executable apunta al propio ejecutable de la app, así que un
    subproceso así relanzaría la app entera en lugar de correr Demucs.
    """
    if not is_demucs_available():
        raise DemucsNotInstalledError(
            "Demucs no está instalado. Instálalo con: pip install -e \".[stems]\""
        )

    from demucs.separate import main as demucs_main

    if device == "auto":
        device = detect_device()

    stems_dir = song_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(f"Iniciando Demucs (modelo={model}, device={device})...")

    opts = ["-n", model, "-d", device, "-o", str(stems_dir), str(source_audio)]

    stream = _ProgressStream(progress_callback)
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = stream  # type: ignore[assignment]
        sys.stderr = stream  # type: ignore[assignment]
        try:
            demucs_main(opts)
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise RuntimeError(f"Demucs terminó con error (code={exc.code})") from None
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    # Demucs guarda en stems_dir/<model>/<nombre_sin_ext>/{vocals,drums,bass,other}.wav
    track_name = source_audio.stem
    result_dir = stems_dir / model / track_name
    stem_files: dict[str, Path] = {}
    for name in ("vocals", "drums", "bass", "other"):
        candidate = result_dir / f"{name}.wav"
        if candidate.exists():
            stem_files[name] = candidate

    if not stem_files:
        raise RuntimeError(f"Demucs no generó stems en la ruta esperada: {result_dir}")

    return StemsResult(stems_dir=result_dir, stem_files=stem_files)
