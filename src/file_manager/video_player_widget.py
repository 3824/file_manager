"""別ウィンドウ用の軽量動画プレーヤーウィジェット。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class VideoPlayerWidget(QWidget):
    """必要時だけ生成する QMediaPlayer ベースの動画プレーヤー。"""

    closed_requested = Signal()

    def __init__(
        self,
        parent=None,
        *,
        default_speed: float = 1.0,
        default_muted: bool = True,
    ) -> None:
        super().__init__(parent)
        self._path: str | None = None
        self._seeking = False
        self._duration = 0
        self._default_speed = default_speed
        self._default_muted = default_muted

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.video_widget = QVideoWidget(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._apply_defaults()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget.setMinimumSize(480, 270)
        layout.addWidget(self.video_widget, 1)

        # ステータスラベル（ファイル名・エラー表示）
        self.status_label = QLabel("動画を読み込んでください")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setObjectName("vpStatusLabel")
        layout.addWidget(self.status_label)

        # シークスライダー
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setObjectName("vpSeekSlider")
        layout.addWidget(self.position_slider)

        # コントロールバー
        ctrl_bar = QWidget()
        ctrl_bar.setObjectName("vpControlBar")
        controls = QHBoxLayout(ctrl_bar)
        controls.setContentsMargins(8, 5, 8, 5)
        controls.setSpacing(4)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("vpIconBtn")
        self.play_button.setFixedSize(30, 26)
        self.play_button.setToolTip("再生 / 一時停止  [Space]")

        self.mute_button = QPushButton("♪")
        self.mute_button.setObjectName("vpIconBtn")
        self.mute_button.setFixedSize(30, 26)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("vpTimeLabel")
        self.time_label.setMinimumWidth(90)

        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("vpSpeedCombo")
        self.speed_combo.setToolTip("再生速度")
        for label, value in [("1.0×", 1.0), ("1.5×", 1.5), ("2.0×", 2.0)]:
            self.speed_combo.addItem(label, value)

        self.open_external_button = QPushButton("外部で開く")
        self.open_external_button.setObjectName("vpSubBtn")
        self.open_external_button.setToolTip("外部プレーヤーで開く")

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("vpIconBtn")
        self.close_button.setFixedSize(26, 26)
        self.close_button.setToolTip("閉じる  [Esc]")

        controls.addWidget(self.play_button)
        controls.addWidget(self.mute_button)
        controls.addWidget(self.time_label, 1)
        controls.addWidget(self.speed_combo)
        controls.addWidget(self.open_external_button)
        controls.addWidget(self.close_button)
        layout.addWidget(ctrl_bar)

    def _connect_signals(self) -> None:
        self.play_button.clicked.connect(self.toggle_playback)
        self.mute_button.clicked.connect(self.toggle_muted)
        self.close_button.clicked.connect(self.closed_requested.emit)
        self.open_external_button.clicked.connect(self.open_external)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.position_slider.sliderPressed.connect(self._on_seek_started)
        self.position_slider.sliderReleased.connect(self._on_seek_finished)
        self.position_slider.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.errorOccurred.connect(self._on_error)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_playback)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.seek_relative(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.seek_relative(5000))
        QShortcut(QKeySequence("M"), self, activated=self.toggle_muted)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.closed_requested.emit)

    def _apply_defaults(self) -> None:
        self.audio_output.setMuted(self._default_muted)
        self._update_mute_button()
        speed_index = self.speed_combo.findData(self._default_speed)
        self.speed_combo.setCurrentIndex(speed_index if speed_index >= 0 else 0)
        self.player.setPlaybackRate(float(self.speed_combo.currentData()))

    def load(self, path: str, *, autoplay: bool = True) -> None:
        self.stop_and_release()
        self._path = path
        self.status_label.setText(Path(path).name)
        self.position_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")
        self.player.setSource(QUrl.fromLocalFile(path))
        if autoplay:
            self.player.play()

    def stop_and_release(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self._duration = 0
        self._path = None

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_muted(self) -> None:
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self._update_mute_button()

    def seek_relative(self, delta_ms: int) -> None:
        if self._duration <= 0:
            return
        position = max(0, min(self._duration, self.player.position() + delta_ms))
        self.player.setPosition(position)

    def open_external(self) -> None:
        if not self._path:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(self._path)):
            QMessageBox.warning(self, "エラー", "外部プレーヤーで開けませんでした。")

    def _on_seek_started(self) -> None:
        self._seeking = True

    def _on_seek_finished(self) -> None:
        self._seeking = False
        self.player.setPosition(self.position_slider.value())

    def _on_position_changed(self, position: int) -> None:
        if not self._seeking:
            self.position_slider.setValue(position)
        self._update_time_label(position, self._duration)

    def _on_duration_changed(self, duration: int) -> None:
        self._duration = max(0, duration)
        self.position_slider.setRange(0, self._duration)
        self._update_time_label(self.player.position(), self._duration)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_speed_changed(self) -> None:
        self.player.setPlaybackRate(float(self.speed_combo.currentData() or 1.0))

    def _on_error(self, error, error_string: str = "") -> None:
        if error == QMediaPlayer.NoError:
            return
        message = error_string or "動画を再生できませんでした。"
        self.status_label.setText(message)
        self.open_external_button.setEnabled(bool(self._path and os.path.exists(self._path)))

    def _update_mute_button(self) -> None:
        muted = self.audio_output.isMuted()
        self.mute_button.setText("✕♪" if muted else "♪")
        self.mute_button.setToolTip("ミュート解除  [M]" if muted else "ミュート  [M]")

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(f"{self._format_ms(position)} / {self._format_ms(duration)}")

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(0, value // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
