"""CH Studio: YouTube -> audio limpio -> stems -> carpeta de Clone Hero."""
import sys

from .settings import CONFIG_DIR

__version__ = "0.1.0"

# Si el usuario actualizó yt-dlp desde la app (ver core/updater.py), la versión nueva
# vive en una carpeta aparte que hay que anteponer al sys.path para que gane sobre la
# que viene empaquetada. Esto tiene que correr antes de cualquier `import yt_dlp` en
# el resto de la app, por eso vive acá (en el __init__ del paquete, lo primero que se
# ejecuta al importar cualquier submódulo de chstudio).
_YTDLP_OVERRIDE_DIR = CONFIG_DIR / "yt-dlp-override"
if (_YTDLP_OVERRIDE_DIR / "yt_dlp").is_dir():
    sys.path.insert(0, str(_YTDLP_OVERRIDE_DIR))
