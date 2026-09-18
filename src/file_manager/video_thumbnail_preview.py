#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動画サムネイルのプレビューウィジェット."""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSpacerItem,
)

try:
    from .video_digest import VideoDigestWorker, VideoDigestGenerator, OPENCV_AVAILABLE
    from .video_digest_cache import VideoDigestCache

    VIDEO_DIGEST_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when optional dependency missing
    VideoDigestWorker = None  # type: ignore
    VideoDigestGenerator = None  # type: ignore
    VideoDigestCache = None  # type: ignore
    OPENCV_AVAILABLE = False
    VIDEO_DIGEST_AVAILABLE = False


class VideoThumbnailPreview(QWidget):
    """選択中の動画ファイルのサムネイルを表示する簡易プレビュー."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        max_thumbnails: int = 6,
        thumbnail_size: tuple[int, int] = (160, 90),
        cache_size_mb: int = 200,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("video-thumbnail-preview")
        self._available = VIDEO_DIGEST_AVAILABLE and VideoDigestWorker is not None
        self._digest_helper = VideoDigestGenerator() if self._available and VideoDigestGenerator else None
        self._max_thumbnails = max_thumbnails
        self._thumbnail_size = thumbnail_size
        self._current_video: Optional[str] = None
        self._worker: Optional[VideoDigestWorker] = None
        self._active_token = 0
        self._token_counter = 0
        self._thumbnail_labels: List[QLabel] = []
        self._thumbnail_cache = ThumbnailMemoryCache()
        self._disk_cache = VideoDigestCache(max_size_mb=cache_size_mb) if VideoDigestCache else None

        self._build_ui()
        self.display_video(None)

    @property
    def is_available(self) -> bool:
        return self._available

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._title_label = QLabel("動画サムネイル")
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title_label.setObjectName("thumbnail-title")
        layout.addWidget(self._title_label)

        frame = QFrame()
        frame.setObjectName("thumbnail-card")
        frame.setFrameShape(QFrame.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(6)

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        frame_layout.addWidget(self._status_label)

        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("thumbnail-scroll-area")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(self._thumbnail_size[1] + 20)

        self._thumb_container = QWidget()
        self._thumb_layout = QHBoxLayout(self._thumb_container)
        self._thumb_layout.setContentsMargins(0, 0, 0, 0)
        self._thumb_layout.setSpacing(8)
        self._thumb_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self._scroll_area.setWidget(self._thumb_container)
        frame_layout.addWidget(self._scroll_area)

        layout.addWidget(frame)

    def set_preferences(
        self,
        *,
        max_thumbnails: Optional[int] = None,
        thumbnail_size: Optional[tuple[int, int]] = None,
        cache_size_mb: Optional[int] = None,
    ) -> None:
        """Update preferred thumbnail parameters and refresh if settings changed."""
        changed = False
        if max_thumbnails is not None:
            try:
                sanitized = int(max_thumbnails)
            except (TypeError, ValueError):
                sanitized = self._max_thumbnails
            else:
                if sanitized < 1:
                    sanitized = 1
            if sanitized != self._max_thumbnails:
                self._max_thumbnails = sanitized
                changed = True
        if thumbnail_size is not None:
            try:
                width, height = thumbnail_size
                width = int(width)
                height = int(height)
            except (TypeError, ValueError):
                width, height = self._thumbnail_size
            if width < 1:
                width = 1
            if height < 1:
                height = 1
            sanitized_size = (width, height)
            if sanitized_size != self._thumbnail_size:
                self._thumbnail_size = sanitized_size
                self._scroll_area.setFixedHeight(self._thumbnail_size[1] + 20)
                changed = True
        if cache_size_mb is not None and self._disk_cache is not None:
            try:
                sanitized_cache_size = max(1, int(cache_size_mb))
            except (TypeError, ValueError):
                sanitized_cache_size = self._disk_cache.max_size_mb
            if sanitized_cache_size != self._disk_cache.max_size_mb:
                self._disk_cache.max_size_mb = sanitized_cache_size
        if changed and self._current_video:
            current = self._current_video
            self._current_video = None
            self.display_video(current)

    def display_video(self, video_path: Optional[str]) -> None:
        """サムネイルを動画パスに合わせて更新."""
        resolved = str(Path(video_path).resolve()) if video_path else None
        if resolved == self._current_video and resolved is not None:
            return

        self._current_video = resolved
        self._active_token += 1
        token = self._active_token

        if not self._available:
            self._show_message("動画ダイジェスト機能が無効のためサムネイルを表示できません", clear_thumbnails=True)
            return

        if not resolved:
            self._show_message("動画を選択するとサムネイルを表示します", clear_thumbnails=True)
            return

        helper = self._digest_helper
        if helper and not helper.is_video_file(resolved):
            name = Path(resolved).name
            self._show_message(f"{name} は動画ファイルではありません", clear_thumbnails=True)
            return

        cache_key = self._cache_key(resolved)
        cached_pixmaps = self._thumbnail_cache.get(cache_key)
        if cached_pixmaps is not None:
            self._handle_digest(token, resolved, cached_pixmaps)
            return
        if self._disk_cache is not None:
            disk_key = self._disk_cache_key(resolved)
            cached_pixmaps = self._disk_cache.get_thumbnails(disk_key)
            if cached_pixmaps is not None:
                self._handle_digest(token, resolved, cached_pixmaps)
                return

        self._show_message("サムネイルを生成中です…", clear_thumbnails=True)
        self._start_worker(resolved, token)

    def clear(self) -> None:
        self.display_video(None)

    def shutdown(self) -> None:
        self._active_token += 1
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.digest_generated.disconnect()
            worker.progress_updated.disconnect()
            worker.error_occurred.disconnect()
            worker.finished.disconnect()
            if not worker.isFinished():
                worker.finished.connect(worker.deleteLater)
            else:
                worker.deleteLater()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------
    def _show_message(self, message: str, *, clear_thumbnails: bool = False) -> None:
        self._status_label.setText(message)
        if clear_thumbnails:
            self._clear_thumbnails()

    def _cache_key(self, video_path: str) -> str:
        return f"{video_path}|{self._max_thumbnails}|{self._thumbnail_size[0]}x{self._thumbnail_size[1]}"

    def _disk_cache_key(self, video_path: str) -> str:
        if self._disk_cache is None:
            return self._cache_key(video_path)
        path = Path(video_path)
        base_key = self._disk_cache.cache_key(path)
        return f"{base_key}_{self._max_thumbnails}_{self._thumbnail_size[0]}x{self._thumbnail_size[1]}"

    def _clear_thumbnails(self) -> None:
        for label in self._thumbnail_labels:
            self._thumb_layout.removeWidget(label)
            label.deleteLater()
        self._thumbnail_labels.clear()

    def _start_worker(self, video_path: str, token: int) -> None:
        worker = VideoDigestWorker(
            video_path,
            max_thumbnails=self._max_thumbnails,
            thumbnail_size=self._thumbnail_size,
            parent=self,
        )
        self._worker = worker

        worker.digest_generated.connect(
            lambda path, pixmaps, tk=token: self._handle_digest(tk, path, pixmaps)
        )
        worker.progress_updated.connect(
            lambda value, tk=token: self._handle_progress(tk, value)
        )
        worker.error_occurred.connect(
            lambda message, tk=token: self._handle_error(tk, message)
        )
        worker.finished.connect(lambda tk=token: self._handle_finished(tk))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _handle_progress(self, token: int, value: int) -> None:
        if token != self._active_token:
            return
        name = Path(self._current_video).name if self._current_video else ""
        suffix = f" {value}%" if value < 100 else ""
        self._status_label.setText(f"{name} のサムネイルを生成中…{suffix}")

    def _handle_digest(self, token: int, video_path: str, pixmaps: Iterable) -> None:
        if token != self._active_token:
            return
        if not self._current_video or Path(video_path).resolve() != Path(self._current_video).resolve():
            return
        self._clear_thumbnails()
        name = Path(video_path).name
        # ワーカーは QImage を送出するため QPixmap に正規化する（QLabel.setPixmap は QPixmap 専用）
        pixmap_list: list[QPixmap] = []
        for p in pixmaps:
            if isinstance(p, QImage):
                pixmap_list.append(QPixmap.fromImage(p))
            else:
                pixmap_list.append(p)
        if not pixmap_list:
            self._status_label.setText(f"{name} のサムネイルを生成できませんでした")
            return
        self._thumbnail_cache.put(self._cache_key(video_path), pixmap_list)
        if self._disk_cache is not None:
            self._disk_cache.put_thumbnails(self._disk_cache_key(video_path), pixmap_list)
        for pixmap in pixmap_list:
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            scaled = pixmap.scaled(
                self._thumbnail_size[0],
                self._thumbnail_size[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            label.setPixmap(scaled)
            label.setFixedSize(self._thumbnail_size[0], self._thumbnail_size[1])
            label.setFrameShape(QFrame.Panel)
            label.setFrameShadow(QFrame.Sunken)
            self._thumb_layout.insertWidget(self._thumb_layout.count() - 1, label)
            self._thumbnail_labels.append(label)
        backend = "OpenCV" if OPENCV_AVAILABLE else "プレースホルダー"
        self._status_label.setText(f"{name} のサムネイル（{backend}）")

    def _handle_error(self, token: int, message: str) -> None:
        if token != self._active_token:
            return
        self._show_message(f"サムネイル生成でエラーが発生しました: {message}", clear_thumbnails=True)

    def _handle_finished(self, token: int) -> None:
        if token == self._active_token:
            self._worker = None


class ThumbnailMemoryCache:
    """動画サムネイルの簡易メモリキャッシュ。"""

    def __init__(self, max_entries: int = 50) -> None:
        self._cache: OrderedDict[str, list[QPixmap]] = OrderedDict()
        self._max_entries = max_entries

    def get(self, video_path: str) -> Optional[list[QPixmap]]:
        cached = self._cache.get(video_path)
        if cached is None:
            return None
        self._cache.move_to_end(video_path)
        return list(cached)

    def put(self, video_path: str, thumbnails: list[QPixmap]) -> None:
        self._cache[video_path] = list(thumbnails)
        self._cache.move_to_end(video_path)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)


__all__ = ["VideoThumbnailPreview", "VIDEO_DIGEST_AVAILABLE", "OPENCV_AVAILABLE"]
