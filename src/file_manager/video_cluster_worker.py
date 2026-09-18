"""動画クラスタリング用バックグラウンドワーカー。

QThread でフォルダスキャン → フレーム抽出 → 埋め込み生成 → DB 保存 → タグ付け →
クラスタリングを順次実行する。キャンセル可能。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from .video_cluster_db import VideoClusterDB
from .video_cluster_engine import (
    ClusterEngine,
    EmbeddingBackend,
    ZeroShotTagger,
    build_backend,
    bytes_to_vec,
    vec_to_bytes,
)

_VIDEO_EXTS = {
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv",
    ".webm", ".m4v", ".3gp", ".mpg", ".mpeg",
}

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def _partial_sha1(path: str, max_bytes: int = 4 * 1024 * 1024) -> str:
    import hashlib
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            h.update(f.read(max_bytes))
    except OSError:
        pass
    return h.hexdigest()


def _extract_frames_cv2(video_path: str, n_frames: int = 8) -> list[np.ndarray]:
    """等間隔でフレームを抽出する（PySceneDetect 非依存の最小実装）。"""
    if not _CV2_AVAILABLE:
        return []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    step = max(1, total // (n_frames + 1))
    frames: list[np.ndarray] = []
    for i in range(1, n_frames + 1):
        pos = step * i
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(frame)
    cap.release()
    return frames


def _get_video_meta(video_path: str) -> dict:
    meta = {"duration": None, "width": None, "height": None, "fps": None}
    if not _CV2_AVAILABLE:
        return meta
    cap = cv2.VideoCapture(video_path)
    if cap.isOpened():
        meta["fps"] = cap.get(cv2.CAP_PROP_FPS) or None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = meta["fps"] or 1.0
        meta["duration"] = total / fps if fps > 0 else None
        meta["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        meta["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
    cap.release()
    return meta


class VideoClusterWorker(QThread):
    """フォルダをスキャンして動画埋め込み・タグ・クラスタを生成する。"""

    # 進捗シグナル
    progress = Signal(int, int, str)       # (current, total, message)
    finished = Signal(int, int)            # (processed, skipped)
    error = Signal(str)

    def __init__(
        self,
        folder: str,
        db: VideoClusterDB,
        *,
        backend: Optional[EmbeddingBackend] = None,
        n_frames: int = 8,
        n_clusters: int = 8,
        force_rescan: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._folder = folder
        self._db = db
        self._backend = backend or build_backend()
        self._n_frames = n_frames
        self._n_clusters = n_clusters
        self._force_rescan = force_rescan
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:
            self.error.emit(str(e))

    def _run(self) -> None:
        # 1. 動画ファイル列挙
        video_paths = self._scan_videos(self._folder)
        total = len(video_paths)
        if total == 0:
            self.finished.emit(0, 0)
            return

        tagger = ZeroShotTagger(self._backend)
        processed = 0
        skipped = 0
        model_name = self._backend.name

        # 2. 各動画を処理
        for i, vpath in enumerate(video_paths):
            if self._cancel:
                break
            self.progress.emit(i, total, f"{Path(vpath).name}")

            try:
                stat = os.stat(vpath)
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                skipped += 1
                continue

            # キャッシュチェック
            if not self._force_rescan and self._db.is_video_cached(vpath, size, mtime):
                skipped += 1
                continue

            # メタデータ取得
            meta = _get_video_meta(vpath)

            # DB に動画登録
            video_id = self._db.upsert_video(
                vpath,
                size=size,
                mtime=mtime,
                duration=meta["duration"],
                width=meta["width"],
                height=meta["height"],
                fps=meta["fps"],
                model_version="v1",
            )

            # フレーム抽出
            frames = _extract_frames_cv2(vpath, self._n_frames)
            if not frames:
                skipped += 1
                continue

            # 埋め込み生成
            frame_vecs = self._backend.encode_frames(frames)

            # 動画ベクトル = フレーム平均
            video_vec = frame_vecs.mean(axis=0) if len(frame_vecs) > 0 else np.zeros(self._backend.dim)
            self._db.replace_embedding("video", video_id, model_name, vec_to_bytes(video_vec), self._backend.dim)

            # タグ付け
            tags = tagger.get_tags(frames, frame_vecs if self._backend.supports_text() else None)
            self._db.delete_video_tags(video_id, source="auto")
            for tag, cat, score in tags:
                self._db.set_video_tag(video_id, tag, category=cat, score=score, source="auto")

            processed += 1

        if self._cancel:
            self.finished.emit(processed, skipped)
            return

        self.progress.emit(total, total, "クラスタリング中...")

        # 3. クラスタリング
        self._run_clustering(model_name)

        self.finished.emit(processed, skipped)

    def _scan_videos(self, folder: str) -> list[str]:
        paths: list[str] = []
        try:
            for dirpath, _dirs, files in os.walk(folder):
                for fname in files:
                    if Path(fname).suffix.lower() in _VIDEO_EXTS:
                        paths.append(os.path.join(dirpath, fname))
        except OSError:
            pass
        return sorted(paths)

    def _run_clustering(self, model_name: str) -> None:
        rows = self._db.get_all_video_embeddings(model_name)
        if len(rows) < 2:
            return
        video_ids = [r[0] for r in rows]
        vecs = np.stack([bytes_to_vec(r[1]) for r in rows], axis=0)

        engine = ClusterEngine(n_clusters=self._n_clusters)
        assignments = engine.cluster(video_ids, vecs)

        self._db.clear_clusters()

        cluster_ids: dict[int, int] = {}
        cluster_tag_pool: dict[int, list[str]] = {}
        for vid, lbl, prob in assignments:
            if lbl not in cluster_ids:
                color = ClusterEngine.CLUSTER_COLORS[lbl % len(ClusterEngine.CLUSTER_COLORS)]
                cid = self._db.create_cluster(f"クラスタ {lbl + 1}", color=color)
                cluster_ids[lbl] = cid
                cluster_tag_pool[lbl] = []
            cid = cluster_ids[lbl]
            self._db.assign_video_cluster(vid, cid, prob)
            # そのクラスタの代表タグを収集
            tags = self._db.get_video_tags(vid)
            for t in tags[:2]:
                cluster_tag_pool[lbl].append(t["canonical_tag"])

        # クラスタ名を代表タグで更新
        for lbl, cid in cluster_ids.items():
            tag_counts: dict[str, int] = {}
            for tag in cluster_tag_pool.get(lbl, []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            top_tags = sorted(tag_counts, key=lambda x: -tag_counts[x])[:3]
            name = engine.auto_name_cluster(lbl, top_tags) if top_tags else f"クラスタ {lbl + 1}"
            self._db.conn.execute("UPDATE clusters SET auto_name=? WHERE id=?", (name, cid))
            self._db.update_cluster_count(cid)
        self._db.conn.commit()
