"""Localización e invocación de ffmpeg/ffprobe."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"


class FFmpegNotFoundError(RuntimeError):
    pass


def find_ffmpeg(configured_path: str = "") -> str:
    """Devuelve la ruta al ejecutable de ffmpeg.

    Orden de búsqueda: ruta configurada por el usuario -> tools/ffmpeg.exe junto a la
    app -> ffmpeg en el PATH del sistema.
    """
    if configured_path:
        p = Path(configured_path)
        if p.is_file():
            return str(p)

    bundled = TOOLS_DIR / ("ffmpeg.exe" if _is_windows() else "ffmpeg")
    if bundled.is_file():
        return str(bundled)

    found = shutil.which("ffmpeg")
    if found:
        return found

    raise FFmpegNotFoundError(
        "No se encontró ffmpeg. Instálalo y agrégalo al PATH, colócalo en "
        f"'{TOOLS_DIR}', o configura la ruta en Ajustes."
    )


def _is_windows() -> bool:
    import sys

    return sys.platform == "win32"


def convert_audio(
    src: Path, dst: Path, ffmpeg_path: str = "", extra_args: list[str] | None = None
) -> None:
    """Convierte/normaliza un archivo de audio con ffmpeg (sobrescribe el destino)."""
    ffmpeg = find_ffmpeg(ffmpeg_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(src)]
    if extra_args:
        cmd += extra_args
    cmd.append(str(dst))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló convirtiendo {src} -> {dst}:\n{result.stderr}")


def to_ogg(src: Path, dst: Path, ffmpeg_path: str = "", quality: int = 5) -> None:
    """Convierte a Ogg Vorbis, formato que usa Clone Hero para stems/song."""
    convert_audio(src, dst, ffmpeg_path, extra_args=["-c:a", "libvorbis", "-q:a", str(quality)])


def probe_duration_seconds(path: Path, ffmpeg_path: str = "") -> float | None:
    """Duración del audio/video en segundos usando ffprobe (junto a ffmpeg)."""
    ffmpeg = find_ffmpeg(ffmpeg_path)
    ffprobe = str(Path(ffmpeg).with_name(Path(ffmpeg).name.replace("ffmpeg", "ffprobe")))
    if not Path(ffprobe).is_file():
        ffprobe = shutil.which("ffprobe") or ""
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None
