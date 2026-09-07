"""Chequeo y actualización de yt-dlp.

YouTube cambia seguido cómo protege sus videos, y una versión vieja de yt-dlp empieza
a fallar con errores como 403. Como yt-dlp es una librería pura Python, en vez de
necesitar pip/venv (como con Demucs+GPU), alcanza con bajar el .whl más nuevo de PyPI
y extraer el paquete a una carpeta aparte que se antepone al sys.path — así se puede
"actualizar" incluso dentro del .exe empaquetado, sin tocar lo que trae adentro.

La carpeta se registra en chstudio/__init__.py, que se ejecuta antes que cualquier
`import yt_dlp` en el resto de la app.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Callable

import requests

from ..settings import CONFIG_DIR

OVERRIDE_DIR = CONFIG_DIR / "yt-dlp-override"
PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"

ProgressCallback = Callable[[str], None]


def get_installed_version() -> str:
    import yt_dlp

    return getattr(yt_dlp.version, "__version__", getattr(yt_dlp, "version", "?"))


def get_latest_version(timeout: float = 8.0) -> str:
    resp = requests.get(PYPI_URL, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["info"]["version"]


def _version_key(version: str) -> tuple:
    """yt-dlp usa versiones tipo 2026.8.19 (a veces con sufijo); las hace comparables."""
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else (0,)


def check_for_update() -> tuple[str, str] | None:
    """Devuelve (version_instalada, version_disponible) si hay una más nueva, si no None.

    No lanza si falla la red: una revisión de versión no debe romper el arranque de
    la app ni asustar al usuario si está sin internet.
    """
    try:
        installed = get_installed_version()
        latest = get_latest_version()
    except Exception:  # noqa: BLE001
        return None

    if _version_key(latest) > _version_key(installed):
        return installed, latest
    return None


def _find_wheel_url(latest: str) -> str:
    resp = requests.get(PYPI_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    for entry in data.get("urls", []):
        if entry.get("packagetype") == "bdist_wheel":
            return entry["url"]
    # Fallback: alguna versión podría no publicar wheel, solo sdist.
    raise RuntimeError(f"No se encontró un .whl para yt-dlp {latest} en PyPI.")


def download_latest(progress_callback: ProgressCallback | None = None) -> str:
    """Baja el último yt-dlp de PyPI y lo deja listo en OVERRIDE_DIR.

    Devuelve la versión instalada. Hace falta reiniciar la app para que tome efecto
    (yt_dlp ya pudo haberse importado en este proceso).
    """

    def report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    report("Consultando última versión en PyPI...")
    latest = get_latest_version()
    wheel_url = _find_wheel_url(latest)

    report(f"Descargando yt-dlp {latest}...")
    resp = requests.get(wheel_url, timeout=60)
    resp.raise_for_status()

    report("Extrayendo...")
    OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for member in zf.namelist():
            if member.startswith("yt_dlp/"):
                zf.extract(member, OVERRIDE_DIR)

    report(f"Listo: yt-dlp {latest} instalado. Reiniciá la app para aplicarlo.")
    return latest
