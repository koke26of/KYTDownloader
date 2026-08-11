"""Escanea la carpeta de salida para listar canciones ya descargadas."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LibrarySong:
    song_dir: Path
    title: str
    artist: str
    source_audio: Path | None
    thumbnail: Path | None
    has_stems: bool
    stems_dir: Path | None
    has_chart: bool
    ch_dir: Path | None


def _parse_folder_name(name: str) -> tuple[str, str]:
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", name


def _find_source_audio(song_dir: Path) -> Path | None:
    for candidate in sorted(song_dir.glob("source.*")):
        if candidate.suffix.lower() not in (".jpg", ".png", ".webp"):
            return candidate
    return None


def _find_thumbnail(song_dir: Path) -> Path | None:
    for ext in ("jpg", "png", "webp"):
        candidate = song_dir / f"source.{ext}"
        if candidate.exists():
            return candidate
    return None


def _find_stems(song_dir: Path) -> Path | None:
    """Busca la carpeta que contiene los .wav de Demucs (vocals/drums/bass/other)."""
    stems_root = song_dir / "stems"
    if not stems_root.exists():
        return None
    vocals = next(stems_root.rglob("vocals.wav"), None)
    return vocals.parent if vocals else None


def scan_library(output_dir: Path) -> list[LibrarySong]:
    """Lista las canciones ya descargadas en output_dir, más reciente primero."""
    if not output_dir.exists():
        return []

    songs = []
    for entry in output_dir.iterdir():
        if not entry.is_dir():
            continue
        artist, title = _parse_folder_name(entry.name)
        source_audio = _find_source_audio(entry)
        stems_dir = _find_stems(entry)
        ch_dir = entry / "chart"
        songs.append(
            LibrarySong(
                song_dir=entry,
                title=title or entry.name,
                artist=artist,
                source_audio=source_audio,
                thumbnail=_find_thumbnail(entry),
                has_stems=stems_dir is not None,
                stems_dir=stems_dir,
                has_chart=(ch_dir / "song.ini").exists(),
                ch_dir=ch_dir if (ch_dir / "song.ini").exists() else None,
            )
        )

    songs.sort(key=lambda s: s.song_dir.stat().st_mtime, reverse=True)
    return songs
