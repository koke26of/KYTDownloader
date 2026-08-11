"""Descarga de audio/video de YouTube usando yt-dlp como librería."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp

ProgressCallback = Callable[[dict], None]


@dataclass
class DownloadResult:
    file_path: Path
    title: str
    artist: str
    duration_seconds: float | None
    thumbnail_path: Path | None
    song_dir: Path


@dataclass
class PlaylistItemOutcome:
    title: str
    success: bool
    result: DownloadResult | None = None
    error: str | None = None


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name).strip()
    return name or "cancion"


def _split_artist_title(title: str, uploader: str) -> tuple[str, str]:
    """Heurística simple: 'Artista - Título' -> (artista, título)."""
    if " - " in title:
        artist, song_title = title.split(" - ", 1)
        return artist.strip(), song_title.strip()
    return uploader.strip() or "Desconocido", title.strip()


def download(
    url: str,
    output_dir: Path,
    mode: str = "audio",  # "audio" | "video"
    audio_format: str = "wav",  # "wav" | "mp3"
    ffmpeg_dir: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DownloadResult:
    """Descarga una URL de YouTube a output_dir/<Artista> - <Título>/.

    Devuelve la ruta al archivo de audio/video resultante junto con metadatos básicos,
    usados luego para armar song.ini.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    hooks = [progress_callback] if progress_callback else []

    # Primero extraemos info sin descargar para poder nombrar la carpeta de forma limpia.
    probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if ffmpeg_dir:
        probe_opts["ffmpeg_location"] = ffmpeg_dir
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if "entries" in info:  # playlist -> tomar el primer entry
            info = info["entries"][0]

    raw_title = info.get("title", "video")
    uploader = info.get("uploader", "")
    artist, song_title = _split_artist_title(raw_title, uploader)
    folder_name = _sanitize_filename(f"{artist} - {song_title}")
    song_dir = output_dir / folder_name
    song_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(song_dir / "source.%(ext)s")

    if mode == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "0" if audio_format == "mp3" else None,
                }
            ],
            "progress_hooks": hooks,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
        }
    else:
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "progress_hooks": hooks,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
        }

    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    ext = audio_format if mode == "audio" else "mp4"
    result_file = song_dir / f"source.{ext}"
    if not result_file.exists():
        # yt-dlp a veces deja el nombre con otra extensión intermedia; buscamos el archivo real.
        candidates = sorted(song_dir.glob("source.*"), key=lambda p: p.stat().st_mtime)
        candidates = [c for c in candidates if c.suffix.lower() not in (".jpg", ".png", ".webp")]
        if candidates:
            result_file = candidates[-1]

    thumbnail = None
    for ext_guess in ("jpg", "png", "webp"):
        candidate = song_dir / f"source.{ext_guess}"
        if candidate.exists():
            thumbnail = candidate
            break

    return DownloadResult(
        file_path=result_file,
        title=song_title,
        artist=artist,
        duration_seconds=info.get("duration"),
        thumbnail_path=thumbnail,
        song_dir=song_dir,
    )


def _playlist_entry_watch_url(entry: dict) -> str:
    video_id = entry.get("id")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    url = entry.get("url", "")
    if url.startswith("http"):
        return url
    return f"https://www.youtube.com/watch?v={url}"


def get_playlist_entries(url: str) -> list[dict] | None:
    """Si la URL es una playlist, devuelve sus entradas (id/título) sin descargar nada.

    Devuelve None si la URL apunta a un solo video (no es una playlist).
    """
    probe_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries")
    if entries is None:
        return None
    # Las entradas de videos privados/eliminados aparecen como None.
    return [e for e in entries if e]


def download_urls(
    url: str,
    output_dir: Path,
    mode: str = "audio",
    audio_format: str = "wav",
    ffmpeg_dir: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[PlaylistItemOutcome]:
    """Descarga una URL de YouTube, cancion por canción si es una playlist.

    Si la URL es de una sola canción, devuelve una lista con un único resultado (mismo
    comportamiento que antes). Si es una playlist, descarga cada canción una por una y
    continúa con las siguientes aunque alguna falle.

    El progress_callback recibe el dict de progreso habitual de yt-dlp, además de las
    claves '_playlist_index', '_playlist_count' y '_playlist_title' para ubicar en qué
    canción de la playlist va la descarga actual.
    """
    entries = get_playlist_entries(url)

    if entries is None:
        def single_hook(d: dict) -> None:
            if progress_callback:
                augmented = dict(d)
                augmented["_playlist_index"] = 1
                augmented["_playlist_count"] = 1
                progress_callback(augmented)

        try:
            result = download(url, output_dir, mode, audio_format, ffmpeg_dir, single_hook)
            return [PlaylistItemOutcome(title=result.title, success=True, result=result)]
        except Exception as exc:  # noqa: BLE001
            return [PlaylistItemOutcome(title=url, success=False, error=str(exc))]

    total = len(entries)
    outcomes: list[PlaylistItemOutcome] = []
    for idx, entry in enumerate(entries, start=1):
        title = entry.get("title") or f"Canción {idx}"
        watch_url = _playlist_entry_watch_url(entry)

        def hook(d: dict, _idx: int = idx, _title: str = title) -> None:
            if progress_callback:
                augmented = dict(d)
                augmented["_playlist_index"] = _idx
                augmented["_playlist_count"] = total
                augmented["_playlist_title"] = _title
                progress_callback(augmented)

        try:
            result = download(watch_url, output_dir, mode, audio_format, ffmpeg_dir, hook)
            outcomes.append(PlaylistItemOutcome(title=result.title, success=True, result=result))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(PlaylistItemOutcome(title=title, success=False, error=str(exc)))

    return outcomes
