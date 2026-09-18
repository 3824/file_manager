import os
import sys

from PySide6.QtGui import QPixmap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_manager.video_digest_cache import VideoDigestCache


def test_video_digest_cache_roundtrip(qapp, tmp_path):
    cache = VideoDigestCache(cache_dir=tmp_path / "cache", max_size_mb=10)
    pixmap = QPixmap(20, 10)
    pixmap.fill()

    cache.put_thumbnails("abc123", [pixmap])
    restored = cache.get_thumbnails("abc123")

    assert restored is not None
    assert len(restored) == 1
    assert not restored[0].isNull()


def test_video_digest_cache_key_changes_when_file_changes(tmp_path):
    cache = VideoDigestCache(cache_dir=tmp_path / "cache", max_size_mb=10)
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"first")

    key1 = cache.cache_key(video)
    video.write_bytes(b"second")
    key2 = cache.cache_key(video)

    assert key1 != key2


def test_video_digest_cache_evicts_oldest(qapp, tmp_path):
    cache = VideoDigestCache(cache_dir=tmp_path / "cache", max_size_mb=1)
    for key in ("a", "b"):
        pixmap = QPixmap(400, 400)
        pixmap.fill()
        cache.put_thumbnails(key, [pixmap])

    cache._index["a"]["last_access"] = 1
    cache._index["b"]["last_access"] = 2
    cache.current_size_bytes = lambda: 2 * 1024 * 1024  # type: ignore[method-assign]
    cache.evict_lru()

    assert len(cache._index) <= 1


def test_video_digest_cache_clear(qapp, tmp_path):
    cache = VideoDigestCache(cache_dir=tmp_path / "cache", max_size_mb=10)
    pixmap = QPixmap(20, 10)
    pixmap.fill()
    cache.put_thumbnails("abc123", [pixmap])

    cache.clear()

    assert cache.get_thumbnails("abc123") is None
    assert cache.current_size_bytes() >= 0
