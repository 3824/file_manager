import file_manager.video_digest as vd
from PySide6.QtGui import QPixmap


def test_video_digest_generator_fallback_without_opencv(qtbot, monkeypatch, tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"dummy")

    monkeypatch.setattr(vd, "OPENCV_AVAILABLE", False, raising=False)

    generator = vd.VideoDigestGenerator()
    results = []
    generator.digest_generated.connect(lambda path, thumbs: results.append((path, thumbs)))

    generator.generate_digest(str(video_path), max_thumbnails=3, thumbnail_size=(80, 45))

    assert results, "digest_generated が発火していません"
    emitted_path, thumbnails = results[0]
    assert emitted_path == str(video_path)
    assert len(thumbnails) == 3
    assert all(isinstance(pix, QPixmap) and not pix.isNull() for pix in thumbnails)


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
    assert all(isinstance(pix, QPixmap) and not pix.isNull() for pix in thumbnails)
