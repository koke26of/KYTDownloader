"""Separador de stems local (drums / bass / other / vocals) con Demucs + Gradio."""
import subprocess
import tempfile
from pathlib import Path

import gradio as gr
import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

OUT_DIR = Path(__file__).parent / "salida"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_models = {}


def load_model(name):
    if name not in _models:
        m = get_model(name)
        m.eval()
        _models[name] = m
    return _models[name]


def read_audio(path):
    """Lee cualquier formato; si soundfile no puede, convierte a wav con ffmpeg."""
    try:
        data, sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        import imageio_ffmpeg
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-i", path, tmp], check=True)
        data, sr = sf.read(tmp, always_2d=True, dtype="float32")
    return data.T, sr  # (canales, muestras)


def resample(wav, sr_in, sr_out):
    if sr_in == sr_out:
        return wav
    import julius
    return julius.resample_frac(wav, sr_in, sr_out)


DL_DIR = Path(__file__).parent / "descargas"


def download(url):
    """Descarga el mejor audio de un link (YouTube, SoundCloud, etc.) con yt-dlp."""
    url = (url or "").strip()
    if not url:
        raise gr.Error("Pega un link primero.")
    import imageio_ffmpeg
    import yt_dlp
    DL_DIR.mkdir(exist_ok=True)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(DL_DIR / "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "js_runtimes": {"deno": {}, "node": {}},  # YouTube necesita un runtime JS
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = info["requested_downloads"][0]["filepath"]
    except Exception as e:
        raise gr.Error(f"No se pudo descargar: {e}")
    return path, path


def separate(audio_path, model_name, progress=gr.Progress(track_tqdm=True)):
    if not audio_path:
        raise gr.Error("Sube un archivo de audio primero.")
    model = load_model(model_name)

    data, sr = read_audio(audio_path)
    wav = torch.from_numpy(data)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    elif wav.shape[0] > 2:
        wav = wav[:2]
    wav = resample(wav, sr, model.samplerate)

    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav_n = (wav - mean) / std

    with torch.no_grad():
        sources = apply_model(model, wav_n[None], device=DEVICE, shifts=1,
                              split=True, overlap=0.25, progress=True)[0]
    sources = sources * std + mean

    out = OUT_DIR / Path(audio_path).stem
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, src in zip(model.sources, sources):
        p = out / f"{name}.wav"
        sf.write(p, np.clip(src.cpu().numpy().T, -1, 1), model.samplerate, subtype="PCM_16")
        paths[name] = str(p)

    return (paths["drums"], paths["bass"], paths["other"], paths["vocals"],
            f"Listo. Guardado en: {out}")


with gr.Blocks(title="Stem Splitter") as demo:
    gr.Markdown(f"# Stem Splitter\nSepara en **drums / bass / other / vocals** localmente. Dispositivo: `{DEVICE}`")
    with gr.Row():
        with gr.Column():
            with gr.Row():
                url = gr.Textbox(label="Link (YouTube, SoundCloud…)", scale=4,
                                 placeholder="https://...")
                dl_btn = gr.Button("Descargar", scale=1)
            # gr.File valida por extensión; gr.Audio usa el MIME del navegador y rechaza .ogg en Windows
            inp = gr.File(label="Audio de entrada", type="filepath",
                          file_types=[".mp3", ".wav", ".flac", ".ogg", ".opus", ".oga", ".m4a",
                                      ".aac", ".webm", ".wma", ".aiff", ".aif", ".mp4", ".mkv"])
            preview = gr.Audio(label="Original", interactive=False)
        with gr.Column():
            model_dd = gr.Dropdown(["htdemucs", "htdemucs_ft"], value="htdemucs",
                                   label="Modelo", info="htdemucs_ft: mejor calidad, ~4x más lento")
            btn = gr.Button("Separar", variant="primary")
            status = gr.Markdown()
    with gr.Row():
        drums = gr.Audio(label="Drums")
        bass = gr.Audio(label="Bass")
    with gr.Row():
        other = gr.Audio(label="Other")
        vocals = gr.Audio(label="Vocals")

    inp.change(lambda p: p, inp, preview)
    dl_btn.click(download, url, [inp, preview])
    url.submit(download, url, [inp, preview])
    btn.click(separate, [inp, model_dd], [drums, bass, other, vocals, status])

if __name__ == "__main__":
    demo.launch(inbrowser=True)
