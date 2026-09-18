"""動画ダイジェスト用ディスクキャッシュ。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QPixmap


class VideoDigestCache:
    """動画ダイジェストのディスクキャッシュ。"""

    def __init__(self, cache_dir: Path | None = None, max_size_mb: int = 200):
        self.cache_dir = cache_dir or self.default_cache_dir()
        self.max_size_mb = max(1, int(max_size_mb))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "cache_index.json"
        self._index = self._load_index()

    @staticmethod
    def default_cache_dir() -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        if not base:
            base = str(Path.cwd() / ".cache")
        return Path(base) / "video_digest"

    def cache_key(self, video_path: Path) -> str:
        stat = video_path.stat()
        raw = f"{video_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_thumbnails(self, key: str) -> list[QPixmap] | None:
        meta = self._index.get(key)
        if not meta:
            return None
        count = int(meta.get("count", 0))
        if count <= 0:
            return None

        key_dir = self._key_dir(key)
        thumbnails: list[QPixmap] = []
        for index in range(count):
            image_path = key_dir / f"{key}_{index}.jpg"
            if not image_path.exists():
                return None
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                return None
            thumbnails.append(pixmap)

        self._touch(key)
        return thumbnails

    def put_thumbnails(self, key: str, thumbnails: list[QPixmap]) -> None:
        if not thumbnails:
            return
        key_dir = self._key_dir(key)
        key_dir.mkdir(parents=True, exist_ok=True)
        for index, pixmap in enumerate(thumbnails):
            pixmap.save(str(key_dir / f"{key}_{index}.jpg"), "JPG", 85)

        self._index[key] = {
            "count": len(thumbnails),
            "last_access": self._next_tick(),
        }
        self._save_index()
        self.evict_lru()

    def clear(self) -> None:
        if self.cache_dir.exists():
            for child in self.cache_dir.iterdir():
                if child.is_dir():
                    for nested in child.iterdir():
                        nested.unlink(missing_ok=True)
                    child.rmdir()
                elif child.is_file():
                    child.unlink(missing_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}
        self._save_index()

    def current_size_bytes(self) -> int:
        total = 0
        if not self.cache_dir.exists():
            return total
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def evict_lru(self) -> None:
        limit_bytes = self.max_size_mb * 1024 * 1024
        while self.current_size_bytes() > limit_bytes and self._index:
            oldest_key = min(self._index.items(), key=lambda item: item[1].get("last_access", 0))[0]
            self._remove_key(oldest_key)
        self._save_index()

    def _key_dir(self, key: str) -> Path:
        return self.cache_dir / key[:2]

    def _remove_key(self, key: str) -> None:
        key_dir = self._key_dir(key)
        for path in key_dir.glob(f"{key}_*.jpg"):
            path.unlink(missing_ok=True)
        self._index.pop(key, None)
        if key_dir.exists() and not any(key_dir.iterdir()):
            key_dir.rmdir()

    def _touch(self, key: str) -> None:
        if key in self._index:
            self._index[key]["last_access"] = self._next_tick()
            self._save_index()

    def _next_tick(self) -> int:
        max_value = max((entry.get("last_access", 0) for entry in self._index.values()), default=0)
        return max_value + 1

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
