"""動画メタデータの SQLite 永続キャッシュ。"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .logger import logger


def _default_db_path() -> str:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    d = base / "FileManager"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / "metadata_cache.db")


class VideoMetadataCache:
    """SQLite を使った動画メタデータの永続キャッシュ。

    インスタンスはメインスレッドからのみ使用すること（check_same_thread=False だが
    QFileSystemModel の data() / update_metadata() は常にメインスレッドから呼ばれる）。
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS metadata_cache (
        path        TEXT    PRIMARY KEY,
        mtime_ns    INTEGER NOT NULL,
        size        INTEGER NOT NULL,
        duration    REAL,
        width       INTEGER,
        height      INTEGER,
        fps         REAL,
        updated_at  REAL    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_updated_at ON metadata_cache (updated_at);
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or _default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path, timeout=5.0, check_same_thread=False
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        try:
            conn = self._connect()
            conn.executescript(self._SCHEMA)
            conn.commit()
        except Exception as e:
            logger.warning(f"VideoMetadataCache: DB 初期化失敗 ({e})")

    def get(self, path: str, mtime_ns: int, size: int) -> Optional[dict]:
        """path / mtime_ns / size が一致するキャッシュエントリを返す。"""
        try:
            row = self._connect().execute(
                "SELECT duration, width, height, fps FROM metadata_cache "
                "WHERE path=? AND mtime_ns=? AND size=?",
                (path, mtime_ns, size),
            ).fetchone()
            if row:
                return {
                    "duration": row[0],
                    "width": row[1],
                    "height": row[2],
                    "fps": row[3],
                }
        except Exception as e:
            logger.debug(f"VideoMetadataCache.get error: {e}")
        return None

    def put(self, path: str, mtime_ns: int, size: int, metadata: dict) -> None:
        """メタデータを保存（既存エントリは置き換える）。"""
        try:
            conn = self._connect()
            conn.execute(
                "INSERT OR REPLACE INTO metadata_cache "
                "(path, mtime_ns, size, duration, width, height, fps, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    path,
                    mtime_ns,
                    size,
                    metadata.get("duration"),
                    metadata.get("width"),
                    metadata.get("height"),
                    metadata.get("fps"),
                    time.time(),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.debug(f"VideoMetadataCache.put error: {e}")

    def cleanup(self, days: int = 30) -> None:
        """`days` 日以上更新されていないエントリを削除する。"""
        try:
            conn = self._connect()
            cutoff = time.time() - days * 86400
            conn.execute("DELETE FROM metadata_cache WHERE updated_at < ?", (cutoff,))
            conn.commit()
        except Exception as e:
            logger.debug(f"VideoMetadataCache.cleanup error: {e}")

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
