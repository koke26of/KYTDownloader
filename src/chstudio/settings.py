"""Configuración persistente de la app.

Se guarda como JSON en %APPDATA%\\ch-studio\\settings.json (en Windows) o en
~/.config/ch-studio/settings.json en otras plataformas, para poder desarrollar/probar
fuera de Windows también.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _default_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "ch-studio"
        return Path.home() / "AppData" / "Roaming" / "ch-studio"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "ch-studio"
    return Path.home() / ".config" / "ch-studio"


def _default_output_dir() -> Path:
    return Path.home() / "Documents" / "CH Studio"


CONFIG_DIR = _default_config_dir()
CONFIG_FILE = CONFIG_DIR / "settings.json"


@dataclass
class Settings:
    output_dir: str = field(default_factory=lambda: str(_default_output_dir()))
    audio_format: str = "wav"  # "wav" o "mp3"
    ffmpeg_path: str = ""  # vacío = buscar en PATH / tools/
    moonscraper_path: str = ""
    editor_on_fire_path: str = ""
    demucs_model: str = "htdemucs"
    demucs_device: str = "auto"  # "auto" | "cpu" | "cuda"
    charter_name: str = ""

    @classmethod
    def load(cls) -> "Settings":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
                return cls(**known)
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def ensure_output_dir(self) -> Path:
        path = Path(self.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
