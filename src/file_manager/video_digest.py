#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動画ダイジェスト生成処理。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from .video_features import extract_thumbnails_with_burst, extract_thumbnails_only

# バーストモード時に前後それぞれ抽出するフレーム数（アニメーション用）
DEFAULT_BURST_COUNT = 3
# アニメーション表示に使う間引きステップ
ANIMATION_STEP = 1

try:
    import cv2
    import numpy as _np

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    _np = None


class VideoDigestGenerator(QObject):
    """動画ダイジェスト生成クラス。"""

    digest_generated = Signal(str, list)
    thumbnail_ready = Signal(int, QImage)        # QImage: スレッドセーフ
    thumbnail_sequence_ready = Signal(int, list) # list[QImage]: スレッドセーフ
    progress_updated = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_extensions = {
            ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv",
            ".webm", ".m4v", ".3gp", ".mpg", ".mpeg",
        }
        self.max_thumbnails = 6
        self.thumbnail_size = (160, 90)
        self.burst_count = 0

    def is_video_file(self, file_path):
        """動画ファイルか判定。"""
        return os.path.isfile(file_path) and Path(file_path).suffix.lower() in self.video_extensions

    def _emit_placeholder_thumbnails(self, video_path, max_thumbnails, thumbnail_size):
        thumbnails = []
        for index in range(max_thumbnails):
            # QImageはスレッドセーフ（QPixmapはGUIスレッド専用のため使用不可）
            image = QImage(thumbnail_size[0], thumbnail_size[1], QImage.Format_RGB888)
            image.fill(QColor(255, 255, 255))
            thumbnails.append(image)
            self.thumbnail_ready.emit(index, image)

        for progress in range(0, 101, max(1, 100 // max(1, max_thumbnails))):
            self.progress_updated.emit(min(progress, 100))

        self.digest_generated.emit(video_path, thumbnails)
        return None

    def _frame_to_image(self, frame, thumbnail_size) -> QImage:
        """OpenCVフレームをQImageに変換（スレッドセーフ）。QPixmapはGUIスレッド専用なので使用禁止。"""
        h_src, w_src = frame.shape[:2]
        if h_src <= 0 or w_src <= 0:
            img = QImage(thumbnail_size[0], thumbnail_size[1], QImage.Format_RGB888)
            img.fill(QColor(30, 30, 30))
            return img

        tw, th = thumbnail_size
        # アスペクト比を保ちながら収まる最大サイズを求める
        scale = min(tw / w_src, th / h_src)
        width = max(1, int(w_src * scale))
        height = max(1, int(h_src * scale))

        # INTER_AREA: 縮小に最適（高速かつ高品質）
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        if width == tw and height == th:
            return QImage(rgb.tobytes(), width, height, rgb.strides[0], QImage.Format_RGB888)

        # numpy キャンバスで余白合成（QPainter より軽量・スレッドセーフ）
        canvas = _np.zeros((th, tw, 3), dtype=_np.uint8)
        y0 = (th - height) // 2
        x0 = (tw - width) // 2
        canvas[y0:y0 + height, x0:x0 + width] = rgb
        return QImage(canvas.tobytes(), tw, th, tw * 3, QImage.Format_RGB888)

    def _make_burst_composite(
        self,
        key_image: QImage,
        burst_list: list,
        thumbnail_size: tuple,
    ) -> QImage:
        """キーフレーム + 前後バーストのフィルムストリップを合成した QImage を生成する（スレッドセーフ）。

        burst_list: [(offset, ndarray), ...] offset 昇順・キーフレーム除く
        """
        if not burst_list:
            return key_image

        key_w, key_h = thumbnail_size
        n = len(burst_list)
        strip_h = max(22, key_h // 3)
        gap = 2
        total_h = key_h + gap + strip_h

        canvas = QImage(key_w, total_h, QImage.Format_RGB888)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter(canvas)

        # キーフレーム（上部）
        painter.drawImage(0, 0, key_image)

        # セパレーター
        painter.fillRect(0, key_h, key_w, gap, QColor(60, 60, 60))

        # フィルムストリップ（各バーストフレームを等幅で配置）
        frame_w = max(1, key_w // n)
        for i, (offset, frame_array) in enumerate(burst_list):
            x = i * frame_w
            cell_w = frame_w if i < n - 1 else key_w - x  # 最後のセルは残り幅
            img = self._frame_to_image(frame_array, (cell_w, strip_h))
            painter.drawImage(x, key_h + gap, img)

            # セル間の区切り線
            if i > 0:
                painter.fillRect(x, key_h + gap, 1, strip_h, QColor(80, 80, 80))

        # キーフレーム位置マーカー（負 → 正 の境目、フィルムストリップ上部に細線）
        pre_count = sum(1 for o, _ in burst_list if o < 0)
        if 0 < pre_count < n:
            marker_x = pre_count * frame_w
            painter.fillRect(marker_x - 1, key_h + gap, 2, strip_h, QColor(255, 200, 0, 200))

        painter.end()
        return canvas

    def generate_digest(self, video_path, max_thumbnails=None, thumbnail_size=None, burst_count=None) -> Optional[None]:
        """サムネイルを生成してシグナル送出する。"""
        if max_thumbnails is None:
            max_thumbnails = self.max_thumbnails
        if thumbnail_size is None:
            thumbnail_size = self.thumbnail_size
        if burst_count is None:
            burst_count = self.burst_count

        if not OPENCV_AVAILABLE:
            return self._emit_placeholder_thumbnails(video_path, max_thumbnails, thumbnail_size)

        if not self.is_video_file(video_path):
            self.error_occurred.emit(f"動画ファイルではありません: {video_path}")
            return None
        if not os.path.exists(video_path):
            self.error_occurred.emit(f"ファイルが見つかりません: {video_path}")
            return None

        try:
            if burst_count == 0:
                # 高速パス: キーフレームのみ（マウスオーバーサムネイルなど）
                extracted_simple = extract_thumbnails_only(
                    video_path,
                    max_thumbnails=max_thumbnails,
                    thumbnail_size=thumbnail_size,
                    progress_callback=lambda v: self.progress_updated.emit(v),
                )
                if not extracted_simple:
                    self.error_occurred.emit(f"サムネイル生成に失敗しました: {video_path}")
                    return None
                thumbnails = []
                for index, (_, key_frame) in enumerate(extracted_simple):
                    key_image = self._frame_to_image(key_frame, thumbnail_size)
                    thumbnails.append(key_image)
                    self.thumbnail_ready.emit(index, key_image)
                self.progress_updated.emit(100)
                self.digest_generated.emit(video_path, thumbnails)
                return None

            # バーストモード: アニメーション付きダイジェスト
            extracted = extract_thumbnails_with_burst(
                video_path,
                max_thumbnails=max_thumbnails,
                thumbnail_size=thumbnail_size,
                burst_count=burst_count,
                progress_callback=lambda value: self.progress_updated.emit(value),
            )
            if not extracted:
                self.error_occurred.emit(f"サムネイル生成に失敗しました: {video_path}")
                return None

            thumbnails = []
            for index, (_, key_frame, burst_list) in enumerate(extracted):
                key_image = self._frame_to_image(key_frame, thumbnail_size)
                pre_frames = [(off, f) for off, f in burst_list if off < 0]
                post_frames = [(off, f) for off, f in burst_list if off > 0]
                sequence: list[QImage] = [
                    self._frame_to_image(f, thumbnail_size)
                    for _, f in pre_frames[::ANIMATION_STEP]
                ]
                sequence.append(key_image)
                sequence.extend(
                    self._frame_to_image(f, thumbnail_size)
                    for _, f in post_frames[::ANIMATION_STEP]
                )
                thumbnails.append(key_image)
                self.thumbnail_sequence_ready.emit(index, sequence)

            self.progress_updated.emit(100)
            self.digest_generated.emit(video_path, thumbnails)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(f"サムネイル生成に失敗しました: {exc}")
        return None

    def get_video_info(self, video_path):
        """動画の基本情報を取得。"""
        if not OPENCV_AVAILABLE or not self.is_video_file(video_path):
            return None

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                cap.release()
                return None
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0
            cap.release()
            return {
                "duration": duration,
                "fps": fps,
                "width": width,
                "height": height,
                "total_frames": total_frames,
                "file_size": os.path.getsize(video_path),
            }
        except Exception:
            return None


class VideoDigestWorker(QThread):
    """動画ダイジェスト生成用ワーカー。"""

    thumbnail_ready = Signal(int, QImage)        # QImage: スレッドセーフ
    thumbnail_sequence_ready = Signal(int, list) # list[QImage]
    digest_generated = Signal(str, list)
    progress_updated = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, video_path, max_thumbnails=6, thumbnail_size=(160, 90), burst_count=0, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.max_thumbnails = max_thumbnails
        self.thumbnail_size = thumbnail_size
        self.burst_count = burst_count
        self.generator = VideoDigestGenerator()
        self.generator.thumbnail_ready.connect(self.thumbnail_ready)
        self.generator.thumbnail_sequence_ready.connect(self.thumbnail_sequence_ready)
        self.generator.digest_generated.connect(self.digest_generated)
        self.generator.progress_updated.connect(self.progress_updated)
        self.generator.error_occurred.connect(self.error_occurred)

    def run(self):
        self.generator.generate_digest(
            self.video_path,
            self.max_thumbnails,
            self.thumbnail_size,
            self.burst_count,
        )
