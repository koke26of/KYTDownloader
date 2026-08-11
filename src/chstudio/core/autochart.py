"""Generación automática de notes.chart.

La parte confiable de esto es el chart de **batería**: al correr sobre el stem de
batería ya aislado por Demucs, detectar golpes y clasificarlos (kick/snare/hi-hat/tom/
platillo) por energía en banda de frecuencia + "ruido" espectral es razonablemente
objetivo, porque cada pieza de la batería ocupa una zona de frecuencia característica.
Esto es mucho más confiable que intentar adivinar notas de guitarra desde una mezcla,
que sigue siendo EXPERIMENTAL y de calidad limitada.
"""
from __future__ import annotations

import re
from pathlib import Path

import librosa
import numpy as np

RESOLUTION = 192  # ticks por negra (resolution estándar de .chart)
DEFAULT_BPM = 120.0
NUM_FRETS = 5

# Mapeo estándar de Clone Hero para el track de batería de 4 pads + kick.
DRUM_LANES = {"kick": 0, "snare": 1, "hihat": 2, "tom": 3, "cymbal": 4}

_SECTION_ORDER = ["Song", "SyncTrack", "Events", "ExpertDrums", "ExpertSingle"]


def _estimate_bpm(y: np.ndarray, sr: int) -> float:
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])
    return bpm if bpm > 0 else DEFAULT_BPM


def _onset_times(y: np.ndarray, sr: int) -> np.ndarray:
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames", backtrack=True)
    return librosa.frames_to_time(onset_frames, sr=sr)


def _seconds_to_ticks(seconds: float, bpm: float) -> int:
    beats = seconds * (bpm / 60.0)
    return int(round(beats * RESOLUTION))


def _fret_for_onset(y: np.ndarray, sr: int, onset_time: float) -> int:
    """Heurística EXPERIMENTAL para guitarra: banda de frecuencia dominante -> traste 0-4."""
    start = librosa.time_to_samples(max(onset_time - 0.02, 0), sr=sr)
    end = librosa.time_to_samples(onset_time + 0.05, sr=sr)
    segment = y[start:end]
    if segment.size == 0:
        return 0
    spectrum = np.abs(np.fft.rfft(segment))
    freqs = np.fft.rfftfreq(segment.size, d=1.0 / sr)
    if spectrum.sum() == 0:
        return 0
    dominant_freq = freqs[np.argmax(spectrum)]
    log_freq = np.log2(max(dominant_freq, 20.0))
    log_min, log_max = np.log2(20.0), np.log2(8000.0)
    ratio = np.clip((log_freq - log_min) / (log_max - log_min), 0, 1)
    return int(round(ratio * (NUM_FRETS - 1)))


def _classify_drum_hit(y: np.ndarray, sr: int, onset_time: float) -> str:
    """Clasifica un golpe de batería por banda de frecuencia dominante + "ruido" espectral.

    Primero se decide la banda dominante (graves/medios/agudos), después se afina con
    spectral flatness (0=tonal, más alto=ruidoso) para separar, por ejemplo, un kick
    (graves, tonal) de un tom grave (graves, algo más ruidoso), o un hi-hat cerrado de
    un platillo abierto (ambos en agudos, pero el platillo es mucho más ruidoso).

    Nota: los umbrales de flatness están calibrados sobre stems reales separados con
    Demucs — librosa.feature.spectral_flatness da valores mucho más bajos en la
    práctica (mediana ~0.01) de lo que su rango teórico [0, 1] sugiere.
    """
    start = librosa.time_to_samples(max(onset_time - 0.005, 0), sr=sr)
    end = librosa.time_to_samples(onset_time + 0.08, sr=sr)
    window = y[start:end]
    if window.size == 0:
        return "tom"

    spectrum = np.abs(np.fft.rfft(window))
    freqs = np.fft.rfftfreq(window.size, d=1.0 / sr)
    total = spectrum.sum()
    if total == 0:
        return "tom"

    low_e = spectrum[freqs < 120].sum() / total
    mid_e = spectrum[(freqs >= 120) & (freqs <= 2500)].sum() / total
    high_e = spectrum[freqs > 2500].sum() / total
    flatness = float(librosa.feature.spectral_flatness(y=window)[0].mean())

    dominant = max(("low", low_e), ("mid", mid_e), ("high", high_e), key=lambda item: item[1])[0]

    if dominant == "high":
        return "cymbal" if (high_e > 0.7 and flatness > 0.05) else "hihat"
    if dominant == "low":
        return "kick" if flatness < 0.02 else "tom"
    # dominant == "mid": tonal (resonancia de parche) -> tom; ruidoso -> snare.
    return "snare" if flatness > 0.008 else "tom"


def _song_section_body(song_name: str, artist: str, charter: str) -> str:
    return "\n".join(
        [
            f'  Name = "{song_name}"',
            f'  Artist = "{artist}"',
            f'  Charter = "{charter or "CH Studio"}"',
            "  Offset = 0",
            f"  Resolution = {RESOLUTION}",
        ]
    )


def _sync_track_body(bpm: float) -> str:
    return "\n".join(["  0 = TS 4", f"  0 = B {int(round(bpm * 1000))}"])


def _read_sections(path: Path) -> dict[str, str]:
    """Parsea un .chart existente en {nombre_sección: cuerpo (sin llaves)}."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for match in re.finditer(r"\[(\w+)\]\s*\{(.*?)\}", text, re.DOTALL):
        sections[match.group(1)] = match.group(2).strip("\n")
    return sections


def _existing_bpm(sections: dict[str, str]) -> float | None:
    body = sections.get("SyncTrack", "")
    match = re.search(r"=\s*B\s+(\d+)", body)
    return int(match.group(1)) / 1000.0 if match else None


def _write_sections(path: Path, sections: dict[str, str]) -> None:
    ordered = [name for name in _SECTION_ORDER if name in sections]
    ordered += [name for name in sections if name not in ordered]
    blocks = [f"[{name}]\n{{\n{sections[name]}\n}}" for name in ordered]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_drum_chart(
    ch_dir: Path,
    drums_audio_path: Path,
    song_name: str,
    artist: str,
    charter: str = "",
) -> Path:
    """Genera (o actualiza) notes.chart con un chart de batería real (ExpertDrums).

    Se corre sobre el stem de batería aislado por Demucs. Preserva otras secciones si
    notes.chart ya existía (por ejemplo un ExpertSingle generado antes a mano).
    """
    dest = ch_dir / "notes.chart"
    sections = _read_sections(dest)

    y, sr = librosa.load(str(drums_audio_path), sr=None, mono=True)
    bpm = _estimate_bpm(y, sr)
    onsets = _onset_times(y, sr)

    note_lines = []
    for onset_time in onsets:
        tick = _seconds_to_ticks(float(onset_time), bpm)
        lane = DRUM_LANES[_classify_drum_hit(y, sr, float(onset_time))]
        note_lines.append(f"  {tick} = N {lane} 0")

    sections["Song"] = _song_section_body(song_name, artist, charter)
    sections["SyncTrack"] = _sync_track_body(bpm)
    sections.setdefault("Events", "")
    sections["ExpertDrums"] = "\n".join(note_lines)

    _write_sections(dest, sections)
    return dest


def write_notes_chart(
    audio_path: Path,
    ch_dir: Path,
    song_name: str,
    artist: str,
    charter: str = "",
    difficulty: str = "ExpertSingle",
) -> Path:
    """EXPERIMENTAL: chart de guitarra/single a partir de onsets de un audio genérico.

    Reutiliza el BPM ya presente en notes.chart si existe (por ejemplo, generado por
    write_drum_chart) para no desincronizar los tracks entre sí; conserva otras
    secciones existentes (no pisa un ExpertDrums ya generado).
    """
    dest = ch_dir / "notes.chart"
    sections = _read_sections(dest)

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    bpm = _existing_bpm(sections) or _estimate_bpm(y, sr)
    onsets = _onset_times(y, sr)

    note_lines = []
    for onset_time in onsets:
        tick = _seconds_to_ticks(float(onset_time), bpm)
        fret = _fret_for_onset(y, sr, float(onset_time))
        note_lines.append(f"  {tick} = N {fret} 0")

    sections["Song"] = _song_section_body(song_name, artist, charter)
    sections["SyncTrack"] = _sync_track_body(bpm)
    sections.setdefault("Events", "")
    sections[difficulty] = "\n".join(note_lines)

    _write_sections(dest, sections)
    return dest
