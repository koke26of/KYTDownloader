"""Organizador de carpeta de canción para Clone Hero: song.ini, song.ogg, stems, album.png."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import autochart, ffmpeg_utils

# Mapeo de nombre de stem (Demucs) -> nombre de archivo que espera Clone Hero.
CH_STEM_NAMES = {
    "drums": "drums.ogg",
    "bass": "bass.ogg",
    "vocals": "vocals.ogg",
    "other": "song.ogg",  # "other" hace de pista base/guitarra+resto si no hay más desglose
}


@dataclass
class SongMetadata:
    name: str
    artist: str
    charter: str = ""
    duration_seconds: float | None = None
    genre: str = ""
    year: str = ""


def build_song_ini(meta: SongMetadata, has_drum_chart: bool = False, has_guitar_chart: bool = False) -> str:
    length_ms = int(meta.duration_seconds * 1000) if meta.duration_seconds else 0
    lines = [
        "[song]",
        f"name = {meta.name}",
        f"artist = {meta.artist}",
        f"charter = {meta.charter or 'CH Studio'}",
        f"song_length = {length_ms}",
    ]
    if meta.genre:
        lines.append(f"genre = {meta.genre}")
    if meta.year:
        lines.append(f"year = {meta.year}")
    # -1 le dice a Clone Hero "este instrumento no tiene chart" (lo oculta en la
    # lista); 0 significa "presente, dificultad sin calcular todavía".
    lines.append(f"diff_guitar = {0 if has_guitar_chart else -1}")
    lines.append(f"diff_drums = {0 if has_drum_chart else -1}")
    return "\n".join(lines) + "\n"


def set_song_ini_diff(ch_dir: Path, key: str, value: int) -> None:
    """Actualiza (o agrega) una línea diff_* en song.ini sin tocar el resto."""
    ini_path = ch_dir / "song.ini"
    if not ini_path.exists():
        return
    lines = ini_path.read_text(encoding="utf-8").splitlines()
    prefix = key.lower()
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith(prefix + " ") or stripped.startswith(prefix + "="):
            lines[i] = f"{key} = {value}"
            break
    else:
        lines.append(f"{key} = {value}")
    ini_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_clone_hero_folder(
    song_dir: Path,
    meta: SongMetadata,
    source_audio: Path,
    stem_files: dict[str, Path] | None = None,
    thumbnail: Path | None = None,
    ffmpeg_path: str = "",
) -> Path:
    """Arma song_dir/chart/ con la estructura estándar de una canción de Clone Hero.

    Si hay stems (de Demucs), los convierte y nombra según lo que espera Clone Hero.
    Si no hay stems, usa el audio original completo como song.ogg.
    """
    ch_dir = song_dir / "chart"
    ch_dir.mkdir(parents=True, exist_ok=True)

    if stem_files:
        for stem_name, ch_name in CH_STEM_NAMES.items():
            src = stem_files.get(stem_name)
            if src is None:
                continue
            dst = ch_dir / ch_name
            ffmpeg_utils.to_ogg(src, dst, ffmpeg_path)
    else:
        dst = ch_dir / "song.ogg"
        ffmpeg_utils.to_ogg(source_audio, dst, ffmpeg_path)

    # El chart de batería se genera automáticamente porque, a diferencia de guitarra,
    # clasificar golpes de batería (kick/snare/hi-hat/tom/platillo) desde un stem
    # aislado es razonablemente objetivo — es la parte confiable del auto-chart.
    has_drum_chart = False
    if stem_files and "drums" in stem_files:
        autochart.write_drum_chart(ch_dir, stem_files["drums"], meta.name, meta.artist, meta.charter)
        has_drum_chart = True

    (ch_dir / "song.ini").write_text(
        build_song_ini(meta, has_drum_chart=has_drum_chart), encoding="utf-8"
    )

    if thumbnail and thumbnail.exists():
        album_dst = ch_dir / "album.png"
        _thumbnail_to_png(thumbnail, album_dst, ffmpeg_path)

    return ch_dir


def _thumbnail_to_png(src: Path, dst: Path, ffmpeg_path: str = "") -> None:
    if src.suffix.lower() == ".png":
        shutil.copyfile(src, dst)
        return
    ffmpeg_utils.convert_audio(src, dst, ffmpeg_path, extra_args=[])


def open_in_editor(ch_dir: Path, editor_path: str) -> None:
    """Lanza Moonscraper / Editor on Fire con el notes.chart de la canción.

    Pasarle solo la carpeta no sirve: estos editores esperan la ruta al archivo de
    chart (como al asociarlo por extensión en el explorador). Sin eso abren un
    proyecto vacío, sin audio ni waveform, aunque los .ogg estén en la misma carpeta.
    """
    if not editor_path:
        raise ValueError("No hay ruta configurada para el editor de charts (ver Ajustes).")
    editor = Path(editor_path)
    if not editor.is_file():
        raise FileNotFoundError(f"No se encontró el editor en: {editor_path}")

    chart_file = ch_dir / "notes.chart"
    if not chart_file.exists():
        raise FileNotFoundError(
            "No hay notes.chart en esta carpeta todavía. Genera la carpeta de Clone Hero "
            "con stems (incluye batería) para crear uno automáticamente."
        )

    subprocess.Popen([str(editor), str(chart_file)])
