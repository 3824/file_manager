"""ファイラー本体から独立した動画プレーヤーウィンドウ。"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from .video_player_widget import VideoPlayerWidget


class VideoPlayerWindow(QDialog):
    """動画再生を別ウィンドウに隔離する軽量ラッパー。"""

    SETTINGS_GROUP = "video_player_window"

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        default_speed: float = 1.0,
        default_muted: bool = True,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or QSettings("FileManager", "Settings")
        self.setWindowTitle("動画プレーヤー")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.player_widget = VideoPlayerWidget(
            self,
            default_speed=default_speed,
            default_muted=default_muted,
        )
        layout.addWidget(self.player_widget)
        self.player_widget.closed_requested.connect(self.close)

        self.resize(QSize(760, 480))
        self._restore_geometry()

    def load_video(self, path: str, *, autoplay: bool = True) -> None:
        self.setWindowTitle(f"動画プレーヤー - {path}")
        self.player_widget.load(path, autoplay=autoplay)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        self.player_widget.stop_and_release()
        super().closeEvent(event)

    def _restore_geometry(self) -> None:
        geometry = self.settings.value(f"{self.SETTINGS_GROUP}/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_geometry(self) -> None:
        self.settings.setValue(f"{self.SETTINGS_GROUP}/geometry", self.saveGeometry())
