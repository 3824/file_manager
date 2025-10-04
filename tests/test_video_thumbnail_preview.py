import os
import sys
import types
from pathlib import Path

import pytest
from PySide6.QtGui import QPixmap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_manager.video_thumbnail_preview import VideoThumbnailPreview


def test_thumbnail_preview_shows_placeholder(qtbot):
    preview = VideoThumbnailPreview()
    qtbot.addWidget(preview)

    preview.display_video(None)

    assert not preview._thumbnail_labels


def test_thumbnail_preview_generates_thumbnails(monkeypatch, qtbot, tmp_path):
    preview = VideoThumbnailPreview()
    qtbot.addWidget(preview)

    if not preview.is_available:
        pytest.skip("Video digest feature is disabled")

    recorded: dict[str, str] = {}

    def fake_start(self, video_path, token):
        recorded["path"] = video_path
        pixmap = QPixmap(20, 10)
        pixmap.fill()
        self._handle_progress(token, 50)
        self._handle_digest(token, video_path, [pixmap])
        self._handle_finished(token)

    monkeypatch.setattr(
        preview,
        "_start_worker",
        types.MethodType(fake_start, preview),
    )

    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"fake")

    preview.display_video(str(video_file))

    assert Path(recorded["path"]).resolve() == video_file.resolve()
    assert preview._thumbnail_labels
    assert preview._thumbnail_labels[0].pixmap() is not None


def test_set_preferences_restarts_current_video(monkeypatch, qtbot, tmp_path):
    preview = VideoThumbnailPreview()
    qtbot.addWidget(preview)

    if not preview.is_available:
        pytest.skip("Video digest feature is disabled")

    calls = {"count": 0}

    def fake_start(self, video_path, token):
        calls["count"] += 1
        pixmap = QPixmap(16, 16)
        pixmap.fill()
        self._handle_digest(token, video_path, [pixmap])
        self._handle_finished(token)

    monkeypatch.setattr(
        preview,
        "_start_worker",
        types.MethodType(fake_start, preview),
    )

    video_file = tmp_path / "pref_sample.mp4"
    video_file.write_bytes(b"fake")

    preview.display_video(str(video_file))
    assert calls["count"] == 1

    calls["count"] = 0
    preview.set_preferences(max_thumbnails=preview._max_thumbnails + 1)

    assert calls["count"] == 1
    assert preview._max_thumbnails >= 2

