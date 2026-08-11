"""Workers en QThread para que las tareas largas no congelen la UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


class _WorkerSignals(QObject):
    # object porque distintas tareas reportan progreso distinto: yt-dlp emite un dict,
    # Demucs emite líneas de texto (str).
    progress = Signal(object)
    finished = Signal(object)
    error = Signal(str)


class FunctionWorker(QThread):
    """Ejecuta una función arbitraria en un hilo aparte, con señales progress/finished/error.

    La función debe aceptar un kwarg opcional `progress_callback` si quiere reportar avance.
    """

    def __init__(self, fn: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            kwargs = dict(self._kwargs)
            kwargs["progress_callback"] = self.signals.progress.emit
            result = self._fn(*self._args, **kwargs)
            self.signals.finished.emit(result)
        except TypeError:
            # La función no acepta progress_callback: reintentar sin él.
            try:
                result = self._fn(*self._args, **self._kwargs)
                self.signals.finished.emit(result)
            except Exception as exc:  # noqa: BLE001
                self.signals.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
