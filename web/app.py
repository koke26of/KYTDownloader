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


NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
# Perfiles de Krumhansl-Kessler para estimar la tonalidad a partir del cromagrama
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
AN_SR = 22050


def to_mono(data, sr):
    import librosa
    y = data.mean(0) if data.ndim == 2 else data
    return librosa.resample(np.ascontiguousarray(y, dtype=np.float32), orig_sr=sr, target_sr=AN_SR)


def estimate_bpm(y):
    import librosa
    hop = 128  # hop pequeño = más resolución temporal en los beats
    onset = librosa.onset.onset_strength(y=y, sr=AN_SR, hop_length=hop)
    bpm, beats = librosa.beat.beat_track(onset_envelope=onset, sr=AN_SR, hop_length=hop)
    bpm = float(np.atleast_1d(bpm)[0])
    if len(beats) >= 8:
        # La estimación base va en pasos discretos; una recta sobre los tiempos de beat la afina
        times = librosa.frames_to_time(beats, sr=AN_SR, hop_length=hop)
        bpm = 60 / np.polyfit(np.arange(len(times)), times, 1)[0]
    while bpm < 70:  # corrige errores de octava (mitad/doble tempo)
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm)


def estimate_key(y, harmonic_only=False):
    import librosa
    if not harmonic_only:
        y = librosa.effects.harmonic(y)
    chroma = librosa.feature.chroma_cqt(y=y, sr=AN_SR).mean(axis=1)
    best = None
    for pc in range(12):
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            r = np.corrcoef(chroma, np.roll(prof, pc))[0, 1]
            if best is None or r > best[0]:
                best = (r, pc, mode)
    _, pc, mode = best
    camelot = ((7 * pc + (8 if mode == "major" else 5)) % 12) or 12
    name = f"{NOTES[pc]} {'Major' if mode == 'major' else 'Minor'}"
    return name, f"{camelot}{'B' if mode == 'major' else 'A'}"


def format_info(bpm, key, camelot, note):
    return f"### 🎵 {bpm} BPM · {key} · Camelot {camelot}\n<sub>{note}</sub>"


def analyze(path):
    """Analiza la mezcla completa al cargar el audio."""
    if not path:
        return path, ""
    data, sr = read_audio(path)
    y = to_mono(data, sr)
    key, cam = estimate_key(y)
    return path, format_info(estimate_bpm(y), key, cam,
                             "Estimado sobre la mezcla. Al separar se recalcula con los stems.")


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

    # Más preciso con stems: BPM desde la batería, tonalidad desde bajo + armonía (sin voz ni batería)
    stems = dict(zip(model.sources, sources.cpu().numpy()))
    bpm = estimate_bpm(to_mono(stems["drums"], model.samplerate))
    key, cam = estimate_key(to_mono(stems["bass"] + stems["other"], model.samplerate),
                            harmonic_only=True)
    info = format_info(bpm, key, cam, "Calculado con los stems (batería → BPM, bajo + other → tonalidad).")

    return (paths["drums"], paths["bass"], paths["other"], paths["vocals"],
            f"Listo. Guardado en: {out}", info)


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
            info_md = gr.Markdown()
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

    # Descargar actualiza inp, y su .change dispara el análisis de BPM/tonalidad
    inp.change(analyze, inp, [preview, info_md])
    dl_btn.click(download, url, [inp, preview])
    url.submit(download, url, [inp, preview])
    btn.click(separate, [inp, model_dd], [drums, bass, other, vocals, status, info_md])

if __name__ == "__main__":
    demo.launch(inbrowser=True)
