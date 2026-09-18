"""動画クラスタリング用 SQLite DB 管理モジュール。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QStandardPaths


def _default_db_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = str(Path.home() / ".file_manager")
    return Path(base) / "video_cluster.db"


class VideoClusterDB:
    """動画クラスタリングのデータを SQLite に永続化するクラス。"""

    SCHEMA_VERSION = 1

    DDL = """
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        size INTEGER,
        mtime REAL,
        partial_sha1 TEXT,
        duration REAL,
        width INTEGER,
        height INTEGER,
        fps REAL,
        scanned_at REAL,
        model_version TEXT DEFAULT 'v1'
    );

    CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        scene_id INTEGER,
        frame_index INTEGER,
        timestamp REAL,
        thumbnail_path TEXT
    );

    CREATE TABLE IF NOT EXISTS embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_type TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        dim INTEGER NOT NULL,
        vector BLOB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_embeddings_owner ON embeddings(owner_type, owner_id);

    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_tag TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        UNIQUE(canonical_tag, category)
    );

    CREATE TABLE IF NOT EXISTS video_tags (
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        score REAL DEFAULT 1.0,
        source TEXT DEFAULT 'auto',
        confirmed_by_user INTEGER DEFAULT 0,
        PRIMARY KEY (video_id, tag_id, source)
    );

    CREATE TABLE IF NOT EXISTS clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auto_name TEXT,
        user_name TEXT,
        centroid BLOB,
        member_count INTEGER DEFAULT 0,
        color TEXT DEFAULT '#6200EE'
    );

    CREATE TABLE IF NOT EXISTS video_clusters (
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
        membership_prob REAL DEFAULT 1.0,
        PRIMARY KEY (video_id, cluster_id)
    );
    """

    def __init__(self, db_path: "Optional[Path | str]" = None):
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._open()
        self._migrate()

    # ------------------------------------------------------------------
    # 接続管理
    # ------------------------------------------------------------------
    def _open(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self.DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._open()
        return self._conn  # type: ignore[return-value]

    def _migrate(self) -> None:
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version VALUES (?)", (self.SCHEMA_VERSION,))
            self.conn.commit()

    # ------------------------------------------------------------------
    # videos
    # ------------------------------------------------------------------
    def upsert_video(
        self,
        path: str,
        *,
        size: Optional[int] = None,
        mtime: Optional[float] = None,
        partial_sha1: Optional[str] = None,
        duration: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        model_version: str = "v1",
    ) -> int:
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO videos (path, size, mtime, partial_sha1, duration, width, height, fps, scanned_at, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                size=excluded.size, mtime=excluded.mtime, partial_sha1=excluded.partial_sha1,
                duration=excluded.duration, width=excluded.width, height=excluded.height,
                fps=excluded.fps, scanned_at=excluded.scanned_at, model_version=excluded.model_version
            """,
            (path, size, mtime, partial_sha1, duration, width, height, fps, now, model_version),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM videos WHERE path=?", (path,)).fetchone()
        return row["id"]

    def get_video_by_path(self, path: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM videos WHERE path=?", (path,)).fetchone()

    def is_video_cached(self, path: str, size: int, mtime: float) -> bool:
        """サイズと mtime が一致すればキャッシュ済みとみなす。"""
        row = self.conn.execute(
            "SELECT id FROM videos WHERE path=? AND size=? AND ABS(mtime-?)<0.1",
            (path, size, mtime),
        ).fetchone()
        return row is not None

    def delete_video(self, path: str) -> None:
        self.conn.execute("DELETE FROM videos WHERE path=?", (path,))
        self.conn.commit()

    def list_videos(self, folder_prefix: str = "") -> list[sqlite3.Row]:
        if folder_prefix:
            like = folder_prefix.rstrip("/\\") + "%"
            return self.conn.execute("SELECT * FROM videos WHERE path LIKE ? ORDER BY path", (like,)).fetchall()
        return self.conn.execute("SELECT * FROM videos ORDER BY path").fetchall()

    # ------------------------------------------------------------------
    # frames
    # ------------------------------------------------------------------
    def insert_frame(
        self,
        video_id: int,
        frame_index: int,
        timestamp: float,
        scene_id: Optional[int] = None,
        thumbnail_path: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO frames (video_id, scene_id, frame_index, timestamp, thumbnail_path) VALUES (?,?,?,?,?)",
            (video_id, scene_id, frame_index, timestamp, thumbnail_path),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_frames(self, video_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM frames WHERE video_id=? ORDER BY frame_index", (video_id,)
        ).fetchall()

    def delete_frames(self, video_id: int) -> None:
        self.conn.execute("DELETE FROM frames WHERE video_id=?", (video_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # embeddings
    # ------------------------------------------------------------------
    def save_embedding(
        self,
        owner_type: str,
        owner_id: int,
        model_name: str,
        vector: bytes,
        dim: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO embeddings (owner_type, owner_id, model_name, dim, vector)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (owner_type, owner_id, model_name, dim, vector),
        )
        self.conn.commit()

    def get_embedding(self, owner_type: str, owner_id: int, model_name: str) -> Optional[bytes]:
        row = self.conn.execute(
            "SELECT vector FROM embeddings WHERE owner_type=? AND owner_id=? AND model_name=?",
            (owner_type, owner_id, model_name),
        ).fetchone()
        return row["vector"] if row else None

    def get_all_video_embeddings(self, model_name: str) -> list[tuple[int, bytes]]:
        """全動画の埋め込み (video_id, vector_blob) リストを返す。"""
        rows = self.conn.execute(
            "SELECT owner_id, vector FROM embeddings WHERE owner_type='video' AND model_name=?",
            (model_name,),
        ).fetchall()
        return [(r["owner_id"], r["vector"]) for r in rows]

    def replace_embedding(
        self,
        owner_type: str,
        owner_id: int,
        model_name: str,
        vector: bytes,
        dim: int,
    ) -> None:
        self.conn.execute(
            "DELETE FROM embeddings WHERE owner_type=? AND owner_id=? AND model_name=?",
            (owner_type, owner_id, model_name),
        )
        self.save_embedding(owner_type, owner_id, model_name, vector, dim)

    # ------------------------------------------------------------------
    # tags
    # ------------------------------------------------------------------
    def get_or_create_tag(self, canonical: str, category: str = "general") -> int:
        row = self.conn.execute(
            "SELECT id FROM tags WHERE canonical_tag=? AND category=?", (canonical, category)
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO tags (canonical_tag, category) VALUES (?,?)", (canonical, category)
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def set_video_tag(
        self,
        video_id: int,
        tag: str,
        *,
        category: str = "general",
        score: float = 1.0,
        source: str = "auto",
        confirmed: bool = False,
    ) -> None:
        tag_id = self.get_or_create_tag(tag, category)
        self.conn.execute(
            """
            INSERT INTO video_tags (video_id, tag_id, score, source, confirmed_by_user)
            VALUES (?,?,?,?,?)
            ON CONFLICT(video_id, tag_id, source) DO UPDATE SET
                score=excluded.score, confirmed_by_user=excluded.confirmed_by_user
            """,
            (video_id, tag_id, score, source, int(confirmed)),
        )
        self.conn.commit()

    def get_video_tags(self, video_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT t.canonical_tag, t.category, vt.score, vt.source, vt.confirmed_by_user
            FROM video_tags vt JOIN tags t ON vt.tag_id=t.id
            WHERE vt.video_id=?
            ORDER BY vt.score DESC
            """,
            (video_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_video_tags(self, video_id: int, source: Optional[str] = None) -> None:
        if source:
            self.conn.execute(
                "DELETE FROM video_tags WHERE video_id=? AND source=?", (video_id, source)
            )
        else:
            self.conn.execute("DELETE FROM video_tags WHERE video_id=?", (video_id,))
        self.conn.commit()

    def get_all_tags_with_counts(self, folder_prefix: str = "") -> list[dict[str, Any]]:
        """タグと動画件数を返す（フィルタ用）。"""
        if folder_prefix:
            like = folder_prefix.rstrip("/\\") + "%"
            rows = self.conn.execute(
                """
                SELECT t.canonical_tag, t.category, COUNT(DISTINCT vt.video_id) as cnt
                FROM tags t
                JOIN video_tags vt ON t.id=vt.tag_id
                JOIN videos v ON vt.video_id=v.id
                WHERE v.path LIKE ?
                GROUP BY t.canonical_tag, t.category
                ORDER BY cnt DESC, t.canonical_tag
                """,
                (like,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT t.canonical_tag, t.category, COUNT(DISTINCT vt.video_id) as cnt
                FROM tags t
                JOIN video_tags vt ON t.id=vt.tag_id
                GROUP BY t.canonical_tag, t.category
                ORDER BY cnt DESC, t.canonical_tag
                """,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_videos_with_tags(self, tags: list[str], folder_prefix: str = "") -> list[str]:
        """指定タグをすべて持つ動画パスを返す（AND フィルタ）。"""
        if not tags:
            return []
        placeholders = ",".join("?" * len(tags))
        base_sql = f"""
            SELECT v.path FROM videos v
            WHERE v.id IN (
                SELECT vt.video_id FROM video_tags vt
                JOIN tags t ON vt.tag_id=t.id
                WHERE t.canonical_tag IN ({placeholders})
                GROUP BY vt.video_id
                HAVING COUNT(DISTINCT t.canonical_tag) >= ?
            )
        """
        params: list[Any] = list(tags) + [len(tags)]
        if folder_prefix:
            base_sql += " AND v.path LIKE ?"
            params.append(folder_prefix.rstrip("/\\") + "%")
        rows = self.conn.execute(base_sql, params).fetchall()
        return [r["path"] for r in rows]

    # ------------------------------------------------------------------
    # clusters
    # ------------------------------------------------------------------
    def clear_clusters(self) -> None:
        self.conn.execute("DELETE FROM video_clusters")
        self.conn.execute("DELETE FROM clusters")
        self.conn.commit()

    def create_cluster(self, auto_name: str, color: str = "#6200EE") -> int:
        cur = self.conn.execute(
            "INSERT INTO clusters (auto_name, color) VALUES (?,?)", (auto_name, color)
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def assign_video_cluster(self, video_id: int, cluster_id: int, prob: float = 1.0) -> None:
        self.conn.execute(
            """
            INSERT INTO video_clusters (video_id, cluster_id, membership_prob)
            VALUES (?,?,?)
            ON CONFLICT(video_id, cluster_id) DO UPDATE SET membership_prob=excluded.membership_prob
            """,
            (video_id, cluster_id, prob),
        )
        self.conn.commit()

    def update_cluster_count(self, cluster_id: int) -> None:
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM video_clusters WHERE cluster_id=?", (cluster_id,)
        ).fetchone()[0]
        self.conn.execute("UPDATE clusters SET member_count=? WHERE id=?", (cnt, cluster_id))
        self.conn.commit()

    def list_clusters(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM clusters ORDER BY member_count DESC").fetchall()

    def get_cluster_videos(self, cluster_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT v.path FROM videos v
            JOIN video_clusters vc ON v.id=vc.video_id
            WHERE vc.cluster_id=?
            ORDER BY vc.membership_prob DESC
            """,
            (cluster_id,),
        ).fetchall()
        return [r["path"] for r in rows]

    # ------------------------------------------------------------------
    # 統計
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {
            "videos": self.conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
            "tags": self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0],
            "clusters": self.conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
        }
