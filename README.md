# CH Studio

App de escritorio (Windows) para agilizar el flujo: **YouTube → audio limpio → stems → carpeta de Clone Hero**.

> Uso personal. Respeta los términos de servicio de YouTube y los derechos de autor del
> contenido que descargues. La app no evade DRM ni está pensada para redistribuir contenido.

## ¿Qué hace?

1. **Descargar**: pega una URL de YouTube y obtén el audio (WAV/MP3) o el video (MP4).
2. **Stems**: dos caminos —
   - *Preparar para Moises*: deja el audio limpio listo para subir manualmente a
     [moises.ai](https://moises.ai) y separar los stems ahí.
   - *Separar local (Demucs)*: separa vocals/drums/bass/other en tu propia PC, sin subir nada.
3. **Clone Hero**: arma automáticamente la carpeta de la canción (`song.ini`, `song.ogg`,
   stems en `.ogg`, `album.png`) y puede abrirla directamente en Moonscraper / Editor on Fire.
4. **Auto-chart (experimental)**: intenta generar un `notes.chart` básico a partir de detección
   de onsets. Calidad limitada — pensado para evaluar la idea, no para charts finales.

## Instalación (desarrollo)

Requisitos previos:
- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) instalado y en el PATH (o colocado en `tools/ffmpeg.exe`)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# Opcional, para separación local de stems (pesado, ~2GB con torch):
pip install -e ".[stems]"
```

Ejecutar:

```bash
python -m chstudio.main
```

## Ajustes

Desde la pestaña **Ajustes** puedes configurar:
- Carpeta de salida por defecto
- Formato de audio (WAV/MP3)
- Rutas a Moonscraper / Editor on Fire
- Modelo de Demucs y dispositivo (CPU/GPU)

La configuración se guarda en `%APPDATA%\ch-studio\settings.json`.

## Empaquetado a .exe

```bash
pip install -e ".[dev]"
pyinstaller packaging/ch-studio.spec
```

El ejecutable queda en `dist/ch-studio/ch-studio.exe`. Nota: si empaquetas con soporte de
Demucs, el bundle será considerablemente más grande por la dependencia de `torch`.
