"""Base compartida entre la app completa (MainWindow) y la básica (BasicMainWindow):
pestañas Descargar y Biblioteca, y el estado de "canción actual".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from chstudio.core import ffmpeg_utils, library, updater
from chstudio.core import downloader as dl
from chstudio.core.library import LibrarySong
from chstudio.core.os_utils import open_folder
from chstudio.settings import Settings
from chstudio.ui.workers import FunctionWorker


@dataclass
class SongState:
    song_dir: Path | None = None
    source_audio: Path | None = None
    title: str = ""
    artist: str = ""
    duration_seconds: float | None = None
    thumbnail: Path | None = None
    stem_files: dict[str, Path] = field(default_factory=dict)
    ch_dir: Path | None = None


class BaseAppWindow(QWidget):
    """No construye pestañas por sí sola: las subclases arman su QTabWidget y llaman
    a _refresh_library() al final de su __init__."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.state = SongState()
        # Lista (no un solo slot) porque ahora puede haber más de un worker a la vez:
        # el chequeo de actualización de yt-dlp corre en paralelo con lo que sea que
        # el usuario esté haciendo. Cada worker se saca solo al terminar.
        self._active_workers: list[FunctionWorker] = []

    # ---------------------------------------------------------------- utils
    def _run(self, fn, *args, on_progress=None, on_finished=None, on_error=None, **kwargs):
        worker = FunctionWorker(fn, *args, **kwargs)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        if on_finished:
            worker.signals.finished.connect(on_finished)

        def _default_error(msg: str) -> None:
            QMessageBox.critical(self, "Error", msg)

        worker.signals.error.connect(on_error or _default_error)

        def _cleanup(*_args: object) -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(_cleanup)
        worker.signals.error.connect(_cleanup)

        self._active_workers.append(worker)  # evita que el GC se lo lleve mientras corre
        worker.start()
        return worker

    def _refresh_song_labels(self) -> None:
        """Hook que las subclases con más pestañas (ej. Stems/Clone Hero) extienden
        vía hasattr; la base solo sabe de lo que ella misma construye."""
        if self.state.song_dir is None:
            return
        if hasattr(self, "stems_song_label"):
            self.stems_song_label.setText(f"Canción actual: {self.state.artist} - {self.state.title}")
        if hasattr(self, "ch_name_input"):
            self.ch_name_input.setText(self.state.title)
            self.ch_artist_input.setText(self.state.artist)

    # ---------------------------------------------------------- tab: Descargar
    def _build_download_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.update_banner = QLabel("")
        self.update_banner.setWordWrap(True)
        self.update_banner.setStyleSheet("color: #b45309; font-weight: bold;")
        self.update_banner.setVisible(False)
        layout.addWidget(self.update_banner)

        self.update_ytdlp_btn = QPushButton("Actualizar yt-dlp ahora")
        self.update_ytdlp_btn.setVisible(False)
        self.update_ytdlp_btn.clicked.connect(self._on_update_ytdlp_clicked)
        layout.addWidget(self.update_ytdlp_btn)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=... o playlist ?list=...")
        layout.addWidget(QLabel("URL de YouTube (video o playlist completa):"))
        layout.addWidget(self.url_input)

        mode_row = QHBoxLayout()
        self.radio_audio = QRadioButton("Audio")
        self.radio_video = QRadioButton("Video")
        self.radio_audio.setChecked(True)
        mode_row.addWidget(self.radio_audio)
        mode_row.addWidget(self.radio_video)

        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["wav", "mp3"])
        mode_row.addWidget(QLabel("Formato audio:"))
        mode_row.addWidget(self.audio_format_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.download_btn = QPushButton("Descargar")
        self.download_btn.clicked.connect(self._on_download_clicked)
        layout.addWidget(self.download_btn)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        layout.addWidget(self.download_progress)

        self.download_status = QLabel("Listo.")
        layout.addWidget(self.download_status)

        self.download_summary = QLabel("")
        self.download_summary.setWordWrap(True)
        layout.addWidget(self.download_summary)

        layout.addWidget(QLabel("Canciones de esta descarga:"))
        self.download_songs_list = QListWidget()
        self.download_songs_list.setMaximumHeight(160)
        layout.addWidget(self.download_songs_list)

        layout.addStretch()

        self._check_ytdlp_update()
        return w

    def _check_ytdlp_update(self) -> None:
        """Corre en segundo plano al abrir la app; si falla (sin internet, etc.) no
        pasa nada, simplemente no se muestra el aviso."""
        self._run(updater.check_for_update, on_finished=self._on_update_check_finished)

    def _on_update_check_finished(self, result: object) -> None:
        if not result:
            return
        installed, latest = result
        self.update_banner.setText(
            f"⚠ yt-dlp desactualizado ({installed} instalada, {latest} disponible). "
            "Las descargas de YouTube pueden fallar (por ejemplo con error 403) hasta "
            "que actualices."
        )
        self.update_banner.setVisible(True)
        self.update_ytdlp_btn.setVisible(True)

    def _on_update_ytdlp_clicked(self) -> None:
        self.update_ytdlp_btn.setEnabled(False)
        self.update_banner.setText("Descargando actualización de yt-dlp...")
        self._run(
            updater.download_latest,
            on_progress=self._on_update_ytdlp_progress,
            on_finished=self._on_update_ytdlp_finished,
            on_error=self._on_update_ytdlp_error,
        )

    def _on_update_ytdlp_progress(self, msg: object) -> None:
        if isinstance(msg, str):
            self.update_banner.setText(msg)

    def _on_update_ytdlp_finished(self, version: object) -> None:
        self.update_ytdlp_btn.setVisible(False)
        self.update_banner.setText(
            f"✓ yt-dlp {version} descargado. Cerrá y volvé a abrir la app para aplicarlo."
        )

    def _on_update_ytdlp_error(self, msg: str) -> None:
        self.update_ytdlp_btn.setEnabled(True)
        self.update_banner.setText("⚠ No se pudo actualizar yt-dlp automáticamente.")
        QMessageBox.critical(self, "Error al actualizar yt-dlp", msg)

    def _on_download_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Falta URL", "Pega una URL de YouTube primero.")
            return

        try:
            ffmpeg_utils.find_ffmpeg(self.settings.ffmpeg_path)
        except ffmpeg_utils.FFmpegNotFoundError as exc:
            QMessageBox.critical(self, "ffmpeg no encontrado", str(exc))
            return

        mode = "audio" if self.radio_audio.isChecked() else "video"
        output_dir = self.settings.ensure_output_dir()

        self.download_btn.setEnabled(False)
        self.download_status.setText("Analizando URL...")
        self.download_progress.setValue(0)
        self.download_summary.setText("")
        self.download_songs_list.clear()

        self._run(
            dl.download_urls,
            url,
            output_dir,
            mode=mode,
            audio_format=self.audio_format_combo.currentText(),
            ffmpeg_dir=str(Path(self.settings.ffmpeg_path).parent) if self.settings.ffmpeg_path else None,
            on_progress=self._on_download_progress,
            on_finished=self._on_download_finished,
            on_error=self._on_download_error,
        )

    def _on_download_progress(self, info: object) -> None:
        if not isinstance(info, dict):
            return
        status = info.get("status")
        idx = info.get("_playlist_index", 1)
        count = info.get("_playlist_count", 1)
        title = info.get("_playlist_title", "")
        prefix = f"[{idx}/{count}] {title} — " if count and count > 1 else ""

        if status == "downloading":
            pct_str = info.get("_percent_str", "").strip().replace("%", "")
            try:
                pct = int(float(pct_str))
                self.download_progress.setValue(min(max(pct, 0), 100))
            except ValueError:
                pass
            speed = info.get("_speed_str", "")
            self.download_status.setText(f"{prefix}Descargando... {speed}".strip())
        elif status == "finished":
            self.download_status.setText(f"{prefix}Procesando (conversión/merge)...")

    def _on_download_finished(self, outcomes: object) -> None:
        assert isinstance(outcomes, list)
        self.download_btn.setEnabled(True)
        self.download_progress.setValue(100)

        ok = [o for o in outcomes if o.success]

        for outcome in outcomes:
            label = f"✓ {outcome.title}" if outcome.success else f"✗ {outcome.title} — {outcome.error}"
            self.download_songs_list.addItem(QListWidgetItem(label))

        if len(outcomes) == 1 and ok:
            # Descarga de un solo video: la dejamos seleccionada como canción actual,
            # igual que antes (compatibilidad con el flujo de una sola canción).
            self._set_current_song_from_download(ok[0].result)
            self.download_status.setText("Descarga completa.")
            self.download_summary.setText(
                f"'{ok[0].result.artist} - {ok[0].result.title}'\nCarpeta: {ok[0].result.song_dir}"
            )
        else:
            self.download_status.setText(
                f"Playlist procesada: {len(ok)} de {len(outcomes)} canciones descargadas."
            )
            self.download_summary.setText(
                "Ve a la pestaña Biblioteca para elegir con qué canción trabajar."
                if ok
                else "No se pudo descargar ninguna canción de la playlist."
            )

        self._refresh_library()

    def _set_current_song_from_download(self, result: dl.DownloadResult) -> None:
        self.state.song_dir = result.song_dir
        self.state.source_audio = result.file_path
        self.state.title = result.title
        self.state.artist = result.artist
        self.state.duration_seconds = result.duration_seconds
        self.state.thumbnail = result.thumbnail_path
        self.state.stem_files = {}
        self.state.ch_dir = None
        self._refresh_song_labels()
        if hasattr(self, "_update_build_folder_gate"):
            self._update_build_folder_gate()

    def _on_download_error(self, msg: str) -> None:
        self.download_status.setText("Error en la descarga.")
        self.download_btn.setEnabled(True)
        QMessageBox.critical(self, "Error al descargar", msg)

    # ------------------------------------------------------------- tab: Biblioteca
    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Canciones ya descargadas en la carpeta de salida:"))

        self.library_list = QListWidget()
        self.library_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.library_list.itemDoubleClicked.connect(lambda _: self._on_use_library_song())
        layout.addWidget(self.library_list)

        actions_row = QHBoxLayout()
        refresh_btn = QPushButton("Actualizar")
        refresh_btn.clicked.connect(self._refresh_library)
        use_btn = QPushButton("Usar esta canción")
        use_btn.clicked.connect(self._on_use_library_song)
        open_btn = QPushButton("Abrir carpeta")
        open_btn.clicked.connect(self._on_open_library_folder)
        actions_row.addWidget(refresh_btn)
        actions_row.addWidget(use_btn)
        actions_row.addWidget(open_btn)
        layout.addLayout(actions_row)

        self.library_status = QLabel("")
        self.library_status.setWordWrap(True)
        layout.addWidget(self.library_status)

        return w

    def _refresh_library(self) -> None:
        output_dir = Path(self.settings.output_dir)
        songs = library.scan_library(output_dir)
        self.library_list.clear()
        for song in songs:
            badges = []
            if song.source_audio:
                badges.append("audio")
            if song.has_stems:
                badges.append("stems")
            if song.has_chart:
                badges.append("chart CH")
            badge_text = f" [{', '.join(badges)}]" if badges else " [vacía]"
            name = f"{song.artist} - {song.title}" if song.artist else song.title
            item = QListWidgetItem(f"{name}{badge_text}")
            item.setData(Qt.UserRole, song)
            self.library_list.addItem(item)
        self.library_status.setText(f"{len(songs)} canción(es) en {output_dir}")

    def _on_use_library_song(self) -> None:
        item = self.library_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Sin selección", "Selecciona una canción de la lista.")
            return
        song: LibrarySong = item.data(Qt.UserRole)

        self.state.song_dir = song.song_dir
        self.state.source_audio = song.source_audio
        self.state.title = song.title
        self.state.artist = song.artist
        self.state.thumbnail = song.thumbnail

        duration = None
        if song.source_audio:
            try:
                duration = ffmpeg_utils.probe_duration_seconds(song.source_audio, self.settings.ffmpeg_path)
            except ffmpeg_utils.FFmpegNotFoundError:
                pass  # song_length quedará en 0 en song.ini; no bloquea seleccionar la canción
        self.state.duration_seconds = duration

        stem_files: dict[str, Path] = {}
        if song.stems_dir:
            for stem_name in ("vocals", "drums", "bass", "other"):
                candidate = song.stems_dir / f"{stem_name}.wav"
                if candidate.exists():
                    stem_files[stem_name] = candidate
        self.state.stem_files = stem_files
        self.state.ch_dir = song.ch_dir

        self._refresh_song_labels()
        if hasattr(self, "_update_build_folder_gate"):
            self._update_build_folder_gate()
        if hasattr(self, "open_editor_btn"):
            self.open_editor_btn.setEnabled(song.ch_dir is not None)
        if hasattr(self, "chart_result_label"):
            self.chart_result_label.setText(
                f"Carpeta de Clone Hero existente: {song.ch_dir}" if song.ch_dir else ""
            )
        self.library_status.setText(f"Canción actual: {self.state.artist} - {self.state.title}")

    def _on_open_library_folder(self) -> None:
        item = self.library_list.currentItem()
        if item is None:
            return
        song: LibrarySong = item.data(Qt.UserRole)
        open_folder(song.song_dir)
