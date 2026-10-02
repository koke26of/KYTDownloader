# KYTDownloader v2 — versión web

Interfaz web local (Gradio) para **descargar audio desde un link y separarlo en stems**
(drums / bass / other / vocals) con Demucs. Todo corre en tu PC; nada se sube a internet.

## ¿Qué hace?

1. **Link**: pega una URL (YouTube, SoundCloud, Bandcamp… cualquier sitio soportado por
   yt-dlp) y descarga el mejor audio disponible.
2. **Archivo**: o sube un archivo local (mp3, wav, flac, ogg, opus, m4a, webm…).
3. **BPM y tonalidad**: al cargar el audio muestra BPM, tonalidad y código Camelot (estilo
   Tunebat), calculados localmente con librosa. Al separar se recalculan con los stems
   (batería → BPM, bajo + other → tonalidad), que es más preciso.
4. **Separar**: obtén 4 stems en WAV, con reproductor en el navegador y descarga directa.

Modelos:
- `htdemucs` — por defecto, rápido.
- `htdemucs_ft` — mejor calidad, ~4x más lento (se descarga la primera vez, ~300 MB).

Usa la GPU NVIDIA automáticamente si está disponible (CUDA); si no, CPU.

## Instalación y uso (Windows)

Requisitos: Python 3.11+. No hace falta instalar ffmpeg (viene incluido vía `imageio-ffmpeg`).

```bat
cd web
setup.bat
run.bat
```

`run.bat` abre la app en el navegador en http://127.0.0.1:7860 (y ejecuta `setup.bat` solo
si aún no existe el entorno).

Salidas:
- `web/descargas/` — audio descargado desde links.
- `web/salida/<canción>/` — stems separados (`drums.wav`, `bass.wav`, `other.wav`, `vocals.wav`).

## Notas

- Si un link de YouTube deja de descargar, actualiza yt-dlp:
  `.venv\Scripts\pip install -U "yt-dlp[default]"`. YouTube además necesita un runtime de
  JavaScript (Deno o Node.js) instalado.
- El audio se lee con `soundfile` y, si el formato no es compatible, se convierte con el ffmpeg
  incluido. No se usa la E/S de `torchaudio`, así que no aplica el problema de TorchCodec.
- Uso personal: respeta los términos de servicio de cada sitio y los derechos de autor.
