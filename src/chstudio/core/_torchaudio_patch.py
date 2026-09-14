"""Parche: reemplaza torchaudio.save por una versión basada en soundfile.

torchaudio >=2.9 delega el guardado de audio a torchcodec, que a su vez necesita una
build de FFmpeg "shared" (con DLLs sueltas) poco común en instalaciones normales —
ni siquiera la que esta misma app instala vía winget la tiene. Cuando falta, Demucs
revienta al guardar los stems con "TorchCodec is required for save_with_torchcodec".

soundfile no depende de FFmpeg para nada, así que evitamos toda esa cadena frágil
reemplazando la función que Demucs llama para guardar .wav/.flac.

SOURCE se guarda como texto (no solo como función de este módulo) porque
core/gpu_env.py necesita aplicarlo también dentro del venv externo con GPU, que corre
en OTRO proceso de Python sin acceso a este paquete.
"""
from __future__ import annotations

SOURCE = """
import torchaudio as _torchaudio
import soundfile as _sf

_ENCODING_TO_SUBTYPE = {
    ("PCM_S", 16): "PCM_16",
    ("PCM_S", 24): "PCM_24",
    ("PCM_S", 32): "PCM_32",
    ("PCM_F", 32): "FLOAT",
}


def _save_with_soundfile(uri, src, sample_rate, channels_first=True, format=None,
                          encoding=None, bits_per_sample=None, **kwargs):
    data = src.detach().cpu().numpy()
    if channels_first:
        data = data.T
    subtype = _ENCODING_TO_SUBTYPE.get((encoding, bits_per_sample), "PCM_16")
    _sf.write(str(uri), data, int(sample_rate), subtype=subtype)


_torchaudio.save = _save_with_soundfile
"""


def apply() -> None:
    """Aplica el parche en el proceso actual (usado por el Demucs CPU integrado)."""
    exec(compile(SOURCE, "<torchaudio_soundfile_patch>", "exec"), {})
