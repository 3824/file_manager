import os
import sys

import numpy as np
from PySide6.QtGui import QImage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import file_manager.video_digest as vd
import file_manager.video_features as vf


def test_video_digest_generator_fallback_without_opencv(qtbot, monkeypatch, tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"dummy")

    monkeypatch.setattr(vd, "OPENCV_AVAILABLE", False, raising=False)

    generator = vd.VideoDigestGenerator()
    results = []
    ready = []
    generator.digest_generated.connect(lambda path, thumbs: results.append((path, thumbs)))
    generator.thumbnail_ready.connect(lambda index, img: ready.append((index, img)))

    generator.generate_digest(str(video_path), max_thumbnails=3, thumbnail_size=(80, 45))

    assert results, "digest_generated が発火していません"
    emitted_path, thumbnails = results[0]
    assert emitted_path == str(video_path)
    assert len(thumbnails) == 3
    assert len(ready) == 3
    assert all(isinstance(img, QImage) and not img.isNull() for img in thumbnails)


def test_video_digest_worker_emits_results_without_opencv(monkeypatch, tmp_path):
    video_path = tmp_path / "worker.mp4"
    video_path.write_bytes(b"dummy")

    monkeypatch.setattr(vd, "OPENCV_AVAILABLE", False, raising=False)

    worker = vd.VideoDigestWorker(str(video_path), max_thumbnails=2, thumbnail_size=(64, 36))
    results = []
    worker.digest_generated.connect(lambda path, thumbs: results.append((path, thumbs)))

    worker.run()

    assert results, "digest_generated が発火していません"
    emitted_path, thumbnails = results[0]
    assert emitted_path == str(video_path)
    assert len(thumbnails) == 2
    assert all(isinstance(img, QImage) and not img.isNull() for img in thumbnails)


def test_extract_thumbnails_only_skips_feature_calculation(monkeypatch, tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"dummy")

    class FakeCapture:
        def __init__(self, _path):
            self._frame = np.zeros((10, 20, 3), dtype=np.uint8)

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == vf.cv2.CAP_PROP_FRAME_COUNT:
                return 60
            return 0

        def set(self, prop, value):
            return True

        def read(self):
            return True, self._frame.copy()

        def release(self):
            return None

    called = {"features": 0}

    monkeypatch.setattr(vf.cv2, "VideoCapture", FakeCapture)
    monkeypatch.setattr(
        vf,
        "compute_frame_features",
        lambda frame: called.__setitem__("features", called["features"] + 1),
    )

    thumbnails = vf.extract_thumbnails_only(str(video_path), max_thumbnails=3, thumbnail_size=(40, 20))

    assert thumbnails is not None
    assert len(thumbnails) == 3
    assert called["features"] == 0


def test_video_digest_worker_emits_sequence_ready(monkeypatch, tmp_path):
    """thumbnail_sequence_ready シグナルが QImage シーケンスを送出することを確認。"""
    video_path = tmp_path / "worker.mp4"
    video_path.write_bytes(b"dummy")

    key_frame = np.zeros((10, 20, 3), dtype=np.uint8)

    monkeypatch.setattr(vd, "OPENCV_AVAILABLE", True, raising=False)
    monkeypatch.setattr(
        vd,
        "extract_thumbnails_with_burst",
        lambda *args, **kwargs: [
            (0.25, key_frame, []),
            (0.75, key_frame, []),
        ],
    )

    worker = vd.VideoDigestWorker(str(video_path), max_thumbnails=2, thumbnail_size=(64, 36), burst_count=1)
    sequences = []
    worker.thumbnail_sequence_ready.connect(lambda index, imgs: sequences.append((index, imgs)))

    worker.run()

    assert [idx for idx, _ in sequences] == [0, 1]
    assert all(isinstance(img, QImage) and not img.isNull() for _, imgs in sequences for img in imgs)


def test_video_digest_worker_emits_burst_sequence(monkeypatch, tmp_path):
    video_path = tmp_path / "burst.mp4"
    video_path.write_bytes(b"dummy")

    key_frame = np.zeros((10, 20, 3), dtype=np.uint8)
    before_frame = np.zeros((10, 20, 3), dtype=np.uint8)
    after_frame = np.zeros((10, 20, 3), dtype=np.uint8)

    monkeypatch.setattr(vd, "OPENCV_AVAILABLE", True, raising=False)
    monkeypatch.setattr(
        vd,
        "extract_thumbnails_with_burst",
        lambda *args, **kwargs: [
            (0.5, key_frame, [(-1, before_frame), (1, after_frame)]),
        ],
    )

    worker = vd.VideoDigestWorker(
        str(video_path),
        max_thumbnails=1,
        thumbnail_size=(64, 36),
        burst_count=1,
    )
    sequences = []
    worker.thumbnail_sequence_ready.connect(
        lambda index, imgs: sequences.append((index, imgs))
    )

    worker.run()

    assert len(sequences) == 1
    index, imgs = sequences[0]
    assert index == 0
    assert len(imgs) == 3
    assert all(isinstance(img, QImage) and not img.isNull() for img in imgs)
