#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動画ダイジェスト表示ダイアログ。"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .utils import silent_warning
from .video_digest import VideoDigestWorker
from .video_digest_cache import VideoDigestCache


class AnimatedThumbnailLabel(QLabel):
    """複数フレームを一定間隔で切り替えるサムネイルラベル。"""

    def __init__(self, frames, interval_ms=180, parent=None):
        super().__init__(parent)
        self._frames = list(frames)
        self._frame_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        if self._frames:
            self.setPixmap(self._frames[0])
        if len(self._frames) > 1:
            self._timer.start(interval_ms)

    def _advance_frame(self):
        if not self._frames:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.setPixmap(self._frames[self._frame_index])


class VideoDigestDialog(QDialog):
    """動画ダイジェスト表示ダイアログ。"""

    def __init__(self, video_path, parent=None):
        real_parent = parent if (parent is not None and hasattr(parent, "window")) else None
        super().__init__(real_parent)
        self.video_path = video_path
        self.settings = QSettings("FileManager", "VideoDigest")
        self.worker = None
        self.thumbnail_widgets = []
        self.disk_cache = None

        # ポップアップダイジェスト専用のフレーム数設定（下部マウスオーバー用とは別）
        self.max_thumbnails = self.settings.value("video_digest_max_frames", 12, type=int)
        self.thumbnail_size = (
            self.settings.value("video_thumbnail_width", 160, type=int),
            self.settings.value("video_thumbnail_height", 90, type=int),
        )
        self.cache_size_mb = self.settings.value("video_digest_cache_size_mb", 200, type=int)
        self.burst_count = self.settings.value("video_digest_burst_count", 0, type=int)
        self.disk_cache = VideoDigestCache(max_size_mb=self.cache_size_mb)

        self.init_ui()
        self.generate_digest()

    def init_ui(self):
        self.setWindowTitle(f"動画ダイジェスト - {os.path.basename(self.video_path)}")
        self.setModal(True)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.create_file_info_section(layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.create_thumbnail_section(layout)
        self.create_button_section(layout)

    def create_file_info_section(self, parent_layout):
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)
        info_layout.setSpacing(2)

        filename_label = QLabel(f"ファイル名: {os.path.basename(self.video_path)}")
        filename_label.setFont(QFont("Arial", 10, QFont.Bold))
        info_layout.addWidget(filename_label)

        path_label = QLabel(f"パス: {self.video_path}")
        path_label.setWordWrap(True)
        info_layout.addWidget(path_label)

        try:
            file_size = os.path.getsize(self.video_path)
            size_mb = file_size / (1024 * 1024)
            info_layout.addWidget(QLabel(f"サイズ: {size_mb:.2f} MB"))
        except OSError:
            pass

        parent_layout.addWidget(info_frame)

    def create_thumbnail_section(self, parent_layout):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QGridLayout(self.thumbnail_container)
        self.thumbnail_layout.setContentsMargins(2, 2, 2, 2)
        self.thumbnail_layout.setSpacing(4)

        scroll_area.setWidget(self.thumbnail_container)
        parent_layout.addWidget(scroll_area)

        self.initial_label = QLabel("ダイジェストを生成中...")
        self.initial_label.setAlignment(Qt.AlignCenter)
        self.initial_label.setStyleSheet("color: gray; font-size: 14px;")
        self.thumbnail_layout.addWidget(self.initial_label, 0, 0)

    def create_button_section(self, parent_layout):
        button_layout = QHBoxLayout()

        self.regenerate_button = QPushButton("再生成")
        self.regenerate_button.clicked.connect(self.regenerate_digest)
        self.regenerate_button.setEnabled(False)
        button_layout.addWidget(self.regenerate_button)

        button_layout.addStretch()

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        parent_layout.addLayout(button_layout)

    def generate_digest(self):
        # アニメーションモードでは常に再生成（静止画キャッシュは使用しない）

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.regenerate_button.setEnabled(False)

        self.worker = VideoDigestWorker(
            self.video_path,
            self.max_thumbnails,
            self.thumbnail_size,
            self.burst_count,
        )
        self.worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.worker.thumbnail_sequence_ready.connect(self.on_thumbnail_sequence_ready)
        self.worker.digest_generated.connect(self.on_digest_generated)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def regenerate_digest(self):
        self.clear_thumbnails()
        self.generate_digest()

    def clear_thumbnails(self):
        while self.thumbnail_layout.count():
            child = self.thumbnail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.thumbnail_widgets = []
        self.initial_label = QLabel("ダイジェストを生成中...")
        self.initial_label.setAlignment(Qt.AlignCenter)
        self.initial_label.setStyleSheet("color: gray; font-size: 14px;")
        self.thumbnail_layout.addWidget(self.initial_label, 0, 0)

    def _create_thumbnail_widget(self, index, thumbnail, frames=None):
        if frames:
            thumbnail_label = AnimatedThumbnailLabel(frames)
        else:
            thumbnail_label = QLabel()
            thumbnail_label.setPixmap(thumbnail)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setStyleSheet("border: 1px solid gray;")
        thumbnail_label.setScaledContents(True)
        thumbnail_label.setFixedSize(self.thumbnail_size[0] + 4, self.thumbnail_size[1] + 4)

        frame_info = QLabel(f"フレーム {index + 1}")
        frame_info.setAlignment(Qt.AlignCenter)
        frame_info.setStyleSheet("font-size: 10px; color: gray;")

        thumbnail_widget = QWidget()
        thumbnail_widget_layout = QVBoxLayout(thumbnail_widget)
        thumbnail_widget_layout.setContentsMargins(1, 1, 1, 1)
        thumbnail_widget_layout.setSpacing(1)
        thumbnail_widget_layout.addWidget(thumbnail_label)
        thumbnail_widget_layout.addWidget(frame_info)
        return thumbnail_widget

    def on_thumbnail_ready(self, index, qimage):
        """ワーカースレッドからQImageを受け取り、メインスレッドでQPixmapに変換して表示。"""
        pixmap = QPixmap.fromImage(qimage)
        self._place_thumbnail(index, pixmap)

    def on_thumbnail_sequence_ready(self, index, qimages):
        """ワーカースレッドからQImageシーケンスを受け取り、メインスレッドでQPixmapに変換してアニメーション表示。"""
        if not qimages:
            return
        pixmaps = [QPixmap.fromImage(img) for img in qimages]
        self._place_animated_thumbnail(index, pixmaps)

    def _place_thumbnail(self, index: int, pixmap: QPixmap):
        """静止サムネイルをグリッドに配置。"""
        if getattr(self, "initial_label", None):
            self.initial_label.deleteLater()
            self.initial_label = None

        while len(self.thumbnail_widgets) <= index:
            self.thumbnail_widgets.append(None)

        widget = self._create_thumbnail_widget(index, pixmap)
        self.thumbnail_widgets[index] = widget
        cols = self._grid_column_count()
        self.thumbnail_layout.addWidget(widget, index // cols, index % cols)

    def _place_animated_thumbnail(self, index: int, pixmaps: list):
        """アニメーションサムネイルをグリッドに配置。"""
        if not pixmaps:
            return
        if getattr(self, "initial_label", None):
            self.initial_label.deleteLater()
            self.initial_label = None

        while len(self.thumbnail_widgets) <= index:
            self.thumbnail_widgets.append(None)

        widget = self._create_thumbnail_widget(index, pixmaps[0], frames=pixmaps)
        self.thumbnail_widgets[index] = widget
        cols = self._grid_column_count()
        self.thumbnail_layout.addWidget(widget, index // cols, index % cols)

    def _grid_column_count(self):
        """サムネイル数に応じたグリッド列数を算出する。多くなりすぎないよう上限8。"""
        count = max(1, int(getattr(self, "max_thumbnails", 6)))
        return max(3, min(8, int(math.ceil(math.sqrt(count)))))

    def on_digest_generated(self, video_path, thumbnails):
        self.regenerate_button.setEnabled(True)
        if not thumbnails:
            self.display_thumbnails([])

    def _disk_cache_key(self):
        base_key = self.disk_cache.cache_key(Path(self.video_path))
        return f"{base_key}_{self.max_thumbnails}_{self.thumbnail_size[0]}x{self.thumbnail_size[1]}_b{self.burst_count}"

    def display_thumbnails(self, thumbnails):
        """キャッシュから読み込んだQPixmapを直接表示（メインスレッドで呼ばれる）。"""
        if thumbnails:
            for index, pixmap in enumerate(thumbnails):
                self._place_thumbnail(index, pixmap)
            return
        no_thumbnails_label = QLabel("サムネイルを生成できませんでした")
        no_thumbnails_label.setAlignment(Qt.AlignCenter)
        no_thumbnails_label.setStyleSheet("color: red; font-size: 14px;")
        self.thumbnail_layout.addWidget(no_thumbnails_label, 0, 0)

    def on_progress_updated(self, progress):
        self.progress_bar.setValue(progress)

    def on_error_occurred(self, error_message):
        silent_warning(self, "エラー", error_message)
        self.progress_bar.setVisible(False)
        self.regenerate_button.setEnabled(True)

    def _resize_to_fit_thumbnails(self):
        """全サムネイルが配置された後にウィンドウサイズをぴったりに合わせる。"""
        n = max(1, sum(1 for w in self.thumbnail_widgets if w is not None))
        cols = self._grid_column_count()
        rows = math.ceil(n / cols)

        tw, th = self.thumbnail_size
        # 1 セルのサイズ: サムネイルラベル(tw+4 x th+4) + フレーム番号ラベル(18px) + レイアウト余白・間隔
        cell_w = tw + 4 + 2       # ラベル境界 + ウィジェット余白
        cell_h = th + 4 + 18 + 3  # ラベル境界 + テキストラベル + 余白・間隔

        # グリッドレイアウト（spacing=4, margins=2+2）
        grid_w = cols * cell_w + max(0, cols - 1) * 4 + 4
        grid_h = rows * cell_h + max(0, rows - 1) * 4 + 4

        # スクロールエリア枠 + 外側 VBox 余白
        scroll_overhead = 24
        # ファイル情報セクション(~82px) + ボタンセクション(~40px) + VBox 余白(~20px)
        fixed_h = 82 + 40 + 20

        dialog_w = max(420, grid_w + scroll_overhead)
        dialog_h = grid_h + scroll_overhead + fixed_h
        self.resize(dialog_w, dialog_h)

    def on_worker_finished(self):
        self.progress_bar.setVisible(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        QTimer.singleShot(50, self._resize_to_fit_thumbnails)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(5000)
            if self.worker.isRunning():
                # terminate()はOpenCVのVideoCapture等を壊す危険があるため使わない。
                # シグナルを切断してスレッドをバックグラウンドで完了させる。
                try:
                    self.worker.thumbnail_ready.disconnect()
                    self.worker.thumbnail_sequence_ready.disconnect()
                    self.worker.progress_updated.disconnect()
                    self.worker.error_occurred.disconnect()
                    self.worker.digest_generated.disconnect()
                except RuntimeError:
                    pass
                self.worker.finished.connect(self.worker.deleteLater)
                self.worker = None
        super().closeEvent(event)
