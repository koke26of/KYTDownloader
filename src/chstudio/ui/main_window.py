"""Ventana principal (versión completa): Descargar | Biblioteca | Stems | Clone Hero | Ajustes."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chstudio.core import autochart, chart, stems
from chstudio.ui.base_window import BaseAppWindow


class MainWindow(BaseAppWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CH Studio")
        self.resize(760, 560)

        tabs = QTabWidget()
        tabs.addTab(self._build_download_tab(), "Descargar")
        tabs.addTab(self._build_library_tab(), "Biblioteca")
        tabs.addTab(self._build_stems_tab(), "Stems")
        tabs.addTab(self._build_chart_tab(), "Clone Hero")
        tabs.addTab(self._build_settings_tab(), "Ajustes")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self._refresh_library()

    # -------------------------------------------------------------- tab: Stems
    def _build_stems_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.stems_song_label = QLabel("No hay canción descargada todavía.")
        self.stems_song_label.setWordWrap(True)
        layout.addWidget(self.stems_song_label)

        moises_box = QGroupBox("Opción 1 (principal): preparar para moises.ai")
        moises_layout = QVBoxLayout(moises_box)
        self.moises_btn = QPushButton("Preparar audio limpio")
        self.moises_btn.clicked.connect(self._on_prepare_moises)
        moises_layout.addWidget(self.moises_btn)

        moises_actions = QHBoxLayout()
        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.clicked.connect(self._on_open_stems_folder)
        self.open_folder_btn.setEnabled(False)
        self.open_moises_btn = QPushButton("Abrir moises.ai")
        self.open_moises_btn.clicked.connect(lambda: stems.open_moises_website())
        moises_actions.addWidget(self.open_folder_btn)
        moises_actions.addWidget(self.open_moises_btn)
        moises_layout.addLayout(moises_actions)
        layout.addWidget(moises_box)

        demucs_box = QGroupBox("Opción 2: separar localmente (Demucs, offline)")
        demucs_layout = QVBoxLayout(demucs_box)
        self.demucs_btn = QPushButton("Separar stems localmente")
        self.demucs_btn.clicked.connect(self._on_separate_local)
        demucs_layout.addWidget(self.demucs_btn)
        self.demucs_log = QTextEdit()
        self.demucs_log.setReadOnly(True)
        self.demucs_log.setMaximumHeight(140)
        demucs_layout.addWidget(self.demucs_log)
        layout.addWidget(demucs_box)

        self.stems_result_label = QLabel("")
        self.stems_result_label.setWordWrap(True)
        layout.addWidget(self.stems_result_label)

        layout.addStretch()
        return w

    def _on_prepare_moises(self) -> None:
        if self.state.source_audio is None or self.state.song_dir is None:
            QMessageBox.warning(self, "Sin canción", "Primero descarga una canción.")
            return
        self.moises_btn.setEnabled(False)
        self._run(
            stems.prepare_for_moises,
            self.state.source_audio,
            self.state.song_dir,
            ffmpeg_path=self.settings.ffmpeg_path,
            audio_format=self.settings.audio_format,
            on_finished=self._on_moises_finished,
        )

    def _on_moises_finished(self, result: object) -> None:
        self.moises_btn.setEnabled(True)
        assert isinstance(result, Path)
        self._moises_output_dir = result.parent
        self.open_folder_btn.setEnabled(True)
        self.stems_result_label.setText(f"Listo para subir a Moises: {result}")

    def _on_open_stems_folder(self) -> None:
        folder = getattr(self, "_moises_output_dir", None)
        if folder:
            stems.open_folder(folder)

    def _on_separate_local(self) -> None:
        if self.state.source_audio is None or self.state.song_dir is None:
            QMessageBox.warning(self, "Sin canción", "Primero descarga una canción.")
            return
        if not stems.is_demucs_available():
            QMessageBox.information(
                self,
                "Demucs no instalado",
                "Para separar stems localmente instala el extra opcional:\n\n"
                'pip install -e ".[stems]"\n\n'
                "(incluye demucs y torch; es una descarga pesada).",
            )
            return

        self.demucs_btn.setEnabled(False)
        self.demucs_log.clear()
        self._run(
            stems.separate_local,
            self.state.source_audio,
            self.state.song_dir,
            model=self.settings.demucs_model,
            device=self.settings.demucs_device,
            on_progress=self._on_demucs_progress,
            on_finished=self._on_demucs_finished,
            on_error=self._on_demucs_error,
        )

    def _on_demucs_progress(self, line: object) -> None:
        if isinstance(line, str):
            self.demucs_log.append(line)

    def _on_demucs_finished(self, result: object) -> None:
        self.demucs_btn.setEnabled(True)
        assert isinstance(result, stems.StemsResult)
        self.state.stem_files = result.stem_files
        names = ", ".join(sorted(result.stem_files))
        self.stems_result_label.setText(f"Stems generados en {result.stems_dir}: {names}")
        self._update_build_folder_gate()

    def _on_demucs_error(self, msg: str) -> None:
        self.demucs_btn.setEnabled(True)
        QMessageBox.critical(self, "Error en Demucs", msg)

    # ---------------------------------------------------------- tab: Clone Hero
    def _build_chart_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        banner = QLabel(
            "🚧 Sección en construcción. Armar la carpeta de Clone Hero y generar el chart "
            "automáticamente (incluida la parte de batería) queda para una futura versión — "
            "el resultado actual todavía está lejos de ser usable. Por ahora, con los stems ya "
            "separados en la pestaña Stems, arma el chart a mano en tu editor."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet("font-weight: bold;")
        layout.addWidget(banner)

        form = QFormLayout()
        self.ch_name_input = QLineEdit()
        self.ch_artist_input = QLineEdit()
        self.ch_charter_input = QLineEdit(self.settings.charter_name)
        form.addRow("Nombre de la canción:", self.ch_name_input)
        form.addRow("Artista:", self.ch_artist_input)
        form.addRow("Charter:", self.ch_charter_input)
        layout.addLayout(form)

        self.build_folder_btn = QPushButton("Generar carpeta de Clone Hero")
        self.build_folder_btn.setEnabled(False)
        self.build_folder_btn.clicked.connect(self._on_build_folder)
        layout.addWidget(self.build_folder_btn)

        self.build_folder_hint = QLabel("")
        self.build_folder_hint.setWordWrap(True)
        layout.addWidget(self.build_folder_hint)

        self.chart_result_label = QLabel("")
        self.chart_result_label.setWordWrap(True)
        layout.addWidget(self.chart_result_label)

        editor_row = QHBoxLayout()
        self.editor_combo = QComboBox()
        self.editor_combo.addItems(["Moonscraper", "Editor on Fire"])
        self.open_editor_btn = QPushButton("Abrir en editor")
        self.open_editor_btn.setEnabled(False)
        self.open_editor_btn.clicked.connect(self._on_open_editor)
        editor_row.addWidget(self.editor_combo)
        editor_row.addWidget(self.open_editor_btn)
        layout.addLayout(editor_row)

        auto_box = QGroupBox("Auto-chart EXPERIMENTAL (detección de onsets, calidad limitada)")
        auto_layout = QVBoxLayout(auto_box)
        auto_warning = QLabel(
            "⚠ Genera un notes.chart de prueba a partir del audio. No reemplaza chartear a mano; "
            "úsalo solo para evaluar la idea."
        )
        auto_warning.setWordWrap(True)
        auto_layout.addWidget(auto_warning)
        self.autochart_btn = QPushButton("Generar notes.chart (experimental)")
        self.autochart_btn.clicked.connect(self._on_autochart)
        auto_layout.addWidget(self.autochart_btn)
        self.autochart_status = QLabel("")
        self.autochart_status.setWordWrap(True)
        auto_layout.addWidget(self.autochart_status)
        layout.addWidget(auto_box)

        layout.addStretch()

        # Toda la sección queda deshabilitada: deshabilitar el contenedor basta (Qt
        # propaga el estado a todos los hijos), sin tocar la lógica interna de cada
        # botón, para poder reactivarla de una cuando se retome esta función.
        w.setEnabled(False)
        return w

    def _update_build_folder_gate(self) -> None:
        has_song = self.state.song_dir is not None
        has_stems = bool(self.state.stem_files)
        self.build_folder_btn.setEnabled(has_song and has_stems)
        if not has_song:
            self.build_folder_hint.setText("")
        elif not has_stems:
            self.build_folder_hint.setText(
                "⚠ Primero separa los stems en la pestaña Stems: el chart de batería se "
                "genera automáticamente a partir del stem de batería aislado."
            )
        else:
            has_drums = "drums" in self.state.stem_files
            self.build_folder_hint.setText(
                ""
                if has_drums
                else "⚠ No hay stem de batería separado; se generará la carpeta pero sin "
                "chart de batería automático."
            )

    def _on_build_folder(self) -> None:
        if self.state.song_dir is None or self.state.source_audio is None:
            QMessageBox.warning(self, "Sin canción", "Primero descarga una canción.")
            return
        if not self.state.stem_files:
            QMessageBox.warning(
                self,
                "Faltan los stems",
                "Separa los stems primero (pestaña Stems). El chart de batería se "
                "arma a partir del stem de batería aislado.",
            )
            return

        meta = chart.SongMetadata(
            name=self.ch_name_input.text().strip() or self.state.title,
            artist=self.ch_artist_input.text().strip() or self.state.artist,
            charter=self.ch_charter_input.text().strip(),
            duration_seconds=self.state.duration_seconds,
        )

        self.build_folder_btn.setEnabled(False)
        self._run(
            chart.build_clone_hero_folder,
            self.state.song_dir,
            meta,
            self.state.source_audio,
            stem_files=self.state.stem_files or None,
            thumbnail=self.state.thumbnail,
            ffmpeg_path=self.settings.ffmpeg_path,
            on_finished=self._on_build_folder_finished,
        )

    def _on_build_folder_finished(self, result: object) -> None:
        self._update_build_folder_gate()
        assert isinstance(result, Path)
        self.state.ch_dir = result
        msg = f"Carpeta de Clone Hero lista en: {result}"
        if "drums" in self.state.stem_files:
            msg += "\n✓ Chart de batería (ExpertDrums) generado automáticamente."
        self.chart_result_label.setText(msg)
        self.open_editor_btn.setEnabled(True)

    def _on_open_editor(self) -> None:
        if self.state.ch_dir is None:
            return
        editor_path = (
            self.settings.moonscraper_path
            if self.editor_combo.currentText() == "Moonscraper"
            else self.settings.editor_on_fire_path
        )
        try:
            chart.open_in_editor(self.state.ch_dir, editor_path)
        except (ValueError, FileNotFoundError) as exc:
            QMessageBox.critical(self, "No se pudo abrir el editor", str(exc))

    def _on_autochart(self) -> None:
        if self.state.ch_dir is None:
            QMessageBox.warning(
                self, "Falta la carpeta", "Genera primero la carpeta de Clone Hero."
            )
            return
        source = self.state.stem_files.get("other", self.state.source_audio)
        if source is None:
            QMessageBox.warning(self, "Sin audio", "No hay audio disponible para chartear.")
            return

        self.autochart_btn.setEnabled(False)
        self.autochart_status.setText("Analizando audio (esto puede tardar)...")
        self._run(
            autochart.write_notes_chart,
            source,
            self.state.ch_dir,
            self.ch_name_input.text().strip() or self.state.title,
            self.ch_artist_input.text().strip() or self.state.artist,
            charter=self.ch_charter_input.text().strip(),
            on_finished=self._on_autochart_finished,
            on_error=self._on_autochart_error,
        )

    def _on_autochart_finished(self, result: object) -> None:
        self.autochart_btn.setEnabled(True)
        self.autochart_status.setText(f"notes.chart (experimental) generado en: {result}")
        if self.state.ch_dir is not None:
            chart.set_song_ini_diff(self.state.ch_dir, "diff_guitar", 0)

    def _on_autochart_error(self, msg: str) -> None:
        self.autochart_btn.setEnabled(True)
        self.autochart_status.setText("Error generando el auto-chart.")
        QMessageBox.critical(self, "Error en auto-chart", msg)

    # ------------------------------------------------------------ tab: Ajustes
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        form = QFormLayout()

        self.out_dir_input = QLineEdit(self.settings.output_dir)
        out_dir_row = QHBoxLayout()
        out_dir_row.addWidget(self.out_dir_input)
        browse_out_btn = QPushButton("...")
        browse_out_btn.clicked.connect(self._browse_output_dir)
        out_dir_row.addWidget(browse_out_btn)
        form.addRow("Carpeta de salida:", out_dir_row)

        self.settings_audio_format = QComboBox()
        self.settings_audio_format.addItems(["wav", "mp3"])
        self.settings_audio_format.setCurrentText(self.settings.audio_format)
        form.addRow("Formato de audio por defecto:", self.settings_audio_format)

        self.ffmpeg_path_input = QLineEdit(self.settings.ffmpeg_path)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_path_input)
        browse_ffmpeg_btn = QPushButton("...")
        browse_ffmpeg_btn.clicked.connect(lambda: self._browse_file(self.ffmpeg_path_input))
        ffmpeg_row.addWidget(browse_ffmpeg_btn)
        form.addRow("Ruta a ffmpeg.exe (opcional):", ffmpeg_row)

        self.moonscraper_path_input = QLineEdit(self.settings.moonscraper_path)
        moonscraper_row = QHBoxLayout()
        moonscraper_row.addWidget(self.moonscraper_path_input)
        browse_moon_btn = QPushButton("...")
        browse_moon_btn.clicked.connect(lambda: self._browse_file(self.moonscraper_path_input))
        moonscraper_row.addWidget(browse_moon_btn)
        form.addRow("Ruta a Moonscraper.exe:", moonscraper_row)

        self.eof_path_input = QLineEdit(self.settings.editor_on_fire_path)
        eof_row = QHBoxLayout()
        eof_row.addWidget(self.eof_path_input)
        browse_eof_btn = QPushButton("...")
        browse_eof_btn.clicked.connect(lambda: self._browse_file(self.eof_path_input))
        eof_row.addWidget(browse_eof_btn)
        form.addRow("Ruta a Editor on Fire.exe:", eof_row)

        self.demucs_model_combo = QComboBox()
        self.demucs_model_combo.addItems(["htdemucs", "htdemucs_ft", "mdx_extra", "mdx_extra_q"])
        self.demucs_model_combo.setCurrentText(self.settings.demucs_model)
        form.addRow("Modelo Demucs:", self.demucs_model_combo)

        self.demucs_device_combo = QComboBox()
        self.demucs_device_combo.addItems(["auto", "cpu", "cuda"])
        self.demucs_device_combo.setCurrentText(self.settings.demucs_device)
        form.addRow("Dispositivo Demucs:", self.demucs_device_combo)

        self.charter_name_input = QLineEdit(self.settings.charter_name)
        form.addRow("Nombre de charter (por defecto):", self.charter_name_input)

        layout.addLayout(form)

        save_btn = QPushButton("Guardar ajustes")
        save_btn.clicked.connect(self._on_save_settings)
        layout.addWidget(save_btn)

        self.settings_status = QLabel("")
        layout.addWidget(self.settings_status)

        layout.addStretch()
        return w

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Elegir carpeta de salida", self.out_dir_input.text())
        if directory:
            self.out_dir_input.setText(directory)

    def _browse_file(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir ejecutable", "", "Ejecutables (*.exe);;Todos (*)")
        if path:
            target.setText(path)

    def _on_save_settings(self) -> None:
        self.settings.output_dir = self.out_dir_input.text().strip() or self.settings.output_dir
        self.settings.audio_format = self.settings_audio_format.currentText()
        self.settings.ffmpeg_path = self.ffmpeg_path_input.text().strip()
        self.settings.moonscraper_path = self.moonscraper_path_input.text().strip()
        self.settings.editor_on_fire_path = self.eof_path_input.text().strip()
        self.settings.demucs_model = self.demucs_model_combo.currentText()
        self.settings.demucs_device = self.demucs_device_combo.currentText()
        self.settings.charter_name = self.charter_name_input.text().strip()
        self.settings.save()
        self.settings_status.setText("Ajustes guardados.")
