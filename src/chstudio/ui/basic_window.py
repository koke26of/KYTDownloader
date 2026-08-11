"""Ventana de la versión Básica: solo Descargar | Biblioteca | Ajustes.

A propósito no importa chstudio.core.stems/chart/autochart (ni librosa/Demucs/torch):
así el .exe empaquetado de esta versión se queda liviano.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chstudio.ui.base_window import BaseAppWindow


class BasicMainWindow(BaseAppWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CH Studio Basic — Descargar de YouTube")
        self.resize(640, 480)

        tabs = QTabWidget()
        tabs.addTab(self._build_download_tab(), "Descargar")
        tabs.addTab(self._build_library_tab(), "Biblioteca")
        tabs.addTab(self._build_settings_tab(), "Ajustes")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self._refresh_library()

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
        self.settings.save()
        self.settings_status.setText("Ajustes guardados.")
