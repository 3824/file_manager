"""動画クラスタリングモジュールの単体テスト。"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# VideoClusterDB
# ---------------------------------------------------------------------------
class TestVideoClusterDB:
    def _make_db(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        return VideoClusterDB(str(tmp_path / "test.db"))

    def test_import(self):
        from file_manager.video_cluster_db import VideoClusterDB  # noqa: F401

    def test_upsert_and_cache_check(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video(
            "/fake/video.mp4",
            size=1000,
            mtime=1700000000.0,
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
        )
        assert isinstance(vid_id, int) and vid_id > 0
        assert db.is_video_cached("/fake/video.mp4", 1000, 1700000000.0)
        assert not db.is_video_cached("/fake/video.mp4", 9999, 1700000000.0)

    def test_set_and_get_tags(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/fake/a.mp4", size=1, mtime=1.0, duration=1.0, width=1, height=1, fps=1.0)
        db.set_video_tag(vid_id, "屋外", category="scene", score=0.9, source="clip", confirmed=False)
        tags = db.get_all_tags_with_counts()
        assert any(t["canonical_tag"] == "屋外" for t in tags)

    def test_get_videos_with_tags(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/fake/b.mp4", size=2, mtime=2.0, duration=2.0, width=2, height=2, fps=2.0)
        db.set_video_tag(vid_id, "人物", category="subject", score=0.8, source="heuristic", confirmed=False)
        paths = db.get_videos_with_tags(["人物"])
        assert "/fake/b.mp4" in paths

    def test_get_videos_with_tags_and_filter(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/fake/sub/c.mp4", size=3, mtime=3.0, duration=3.0, width=3, height=3, fps=3.0)
        db.set_video_tag(vid_id, "風景", category="scene", score=0.7, source="clip", confirmed=False)
        # folder_prefix matches
        assert "/fake/sub/c.mp4" in db.get_videos_with_tags(["風景"], folder_prefix="/fake/sub")
        # folder_prefix doesn't match
        assert "/fake/sub/c.mp4" not in db.get_videos_with_tags(["風景"], folder_prefix="/other")

    def test_cluster_crud(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/fake/d.mp4", size=4, mtime=4.0, duration=4.0, width=4, height=4, fps=4.0)
        cid = db.create_cluster("テストクラスタ", "#6200EE")
        assert isinstance(cid, int) and cid > 0
        db.assign_video_cluster(vid_id, cid, 0.95)
        videos = db.get_cluster_videos(cid)
        assert "/fake/d.mp4" in videos

    def test_stats(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        s = db.stats()
        assert "videos" in s and "tags" in s and "clusters" in s
        assert s["videos"] == 0

    def test_clear_clusters(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        db.create_cluster("X", "#FF0000")
        assert db.stats()["clusters"] == 1
        db.clear_clusters()
        assert db.stats()["clusters"] == 0

    def test_list_clusters(self, tmp_path):
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        db.create_cluster("Alpha", "#6200EE")
        db.create_cluster("Beta", "#03DAC6")
        clusters = db.list_clusters()
        names = [c["auto_name"] for c in clusters]
        assert "Alpha" in names and "Beta" in names

    def test_embedding_round_trip(self, tmp_path):
        import numpy as np
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/fake/e.mp4", size=5, mtime=5.0, duration=5.0, width=5, height=5, fps=5.0)
        vec = np.random.rand(128).astype(np.float32)
        db.save_embedding("video", vid_id, "color_hist_v1", vec.tobytes(), 128)
        rows = db.get_all_video_embeddings("color_hist_v1")
        assert len(rows) == 1
        assert rows[0][0] == vid_id
        restored = np.frombuffer(rows[0][1], dtype=np.float32)
        assert np.allclose(restored, vec)


# ---------------------------------------------------------------------------
# ColorHistogramBackend
# ---------------------------------------------------------------------------
class TestColorHistogramBackend:
    def test_import(self):
        from file_manager.video_cluster_engine import ColorHistogramBackend  # noqa: F401

    def test_name_and_dim(self):
        from file_manager.video_cluster_engine import ColorHistogramBackend
        b = ColorHistogramBackend()
        assert b.name == "color_hist_v1"
        assert b.dim == 128

    def test_encode_frames(self):
        import numpy as np
        import cv2
        from file_manager.video_cluster_engine import ColorHistogramBackend
        b = ColorHistogramBackend()
        # 2 random BGR frames
        frames = [np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8) for _ in range(2)]
        vecs = b.encode_frames(frames)
        assert vecs.shape == (2, 128)
        # L2 normalized
        norms = np.linalg.norm(vecs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_embed_single_frame(self):
        import numpy as np
        from file_manager.video_cluster_engine import ColorHistogramBackend
        b = ColorHistogramBackend()
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        vecs = b.encode_frames([frame])
        assert vecs.shape == (1, 128)


# ---------------------------------------------------------------------------
# ZeroShotTagger (heuristic path only)
# ---------------------------------------------------------------------------
class TestZeroShotTagger:
    def test_import(self):
        from file_manager.video_cluster_engine import ZeroShotTagger  # noqa: F401

    def test_get_tags_heuristic(self):
        import numpy as np
        from file_manager.video_cluster_engine import ZeroShotTagger
        tagger = ZeroShotTagger(backend=None)  # force heuristic
        frames = [np.zeros((64, 64, 3), dtype=np.uint8)]  # dark frame
        tags = tagger.get_tags(frames)
        assert isinstance(tags, list)
        # dark frames should get "夜景" or "暗い" type tags
        # At minimum a list is returned (may be empty depending on thresholds)

    def test_tags_format(self):
        import numpy as np
        from file_manager.video_cluster_engine import ZeroShotTagger
        tagger = ZeroShotTagger(backend=None)
        frames = [np.full((64, 64, 3), 200, dtype=np.uint8)]  # bright frame
        tags = tagger.get_tags(frames)
        for item in tags:
            assert len(item) == 3  # (tag, category, score)
            tag, category, score = item
            assert isinstance(tag, str)
            assert isinstance(category, str)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# ClusterEngine
# ---------------------------------------------------------------------------
class TestClusterEngine:
    def test_import(self):
        from file_manager.video_cluster_engine import ClusterEngine  # noqa: F401

    def test_cluster_returns_assignments(self):
        import numpy as np
        from file_manager.video_cluster_engine import ClusterEngine
        engine = ClusterEngine(n_clusters=2)
        video_ids = [1, 2, 3, 4, 5, 6]
        embeddings = np.random.rand(6, 128).astype(np.float32)
        assignments = engine.cluster(video_ids, embeddings)
        assert len(assignments) == 6
        for vid_id, cluster_id, prob in assignments:
            assert vid_id in video_ids
            assert isinstance(cluster_id, int)
            assert 0.0 <= prob <= 1.0

    def test_cluster_fewer_than_k(self):
        import numpy as np
        from file_manager.video_cluster_engine import ClusterEngine
        engine = ClusterEngine(n_clusters=5)
        video_ids = [10, 11]
        embeddings = np.random.rand(2, 128).astype(np.float32)
        assignments = engine.cluster(video_ids, embeddings)
        # Should still return assignments (k capped to n_videos)
        assert len(assignments) == 2

    def test_cluster_single_video(self):
        import numpy as np
        from file_manager.video_cluster_engine import ClusterEngine
        engine = ClusterEngine(n_clusters=3)
        video_ids = [99]
        embeddings = np.random.rand(1, 128).astype(np.float32)
        assignments = engine.cluster(video_ids, embeddings)
        assert len(assignments) == 1


# ---------------------------------------------------------------------------
# FileSortFilterProxyModel — タグフィルタ拡張
# ---------------------------------------------------------------------------
class TestFileSortFilterProxyModelTagFilter:
    def test_import(self):
        from file_manager.qt_models import FileSortFilterProxyModel  # noqa: F401

    def test_set_tag_filter_no_crash(self):
        from file_manager.qt_models import FileSortFilterProxyModel
        proxy = FileSortFilterProxyModel()
        proxy.set_tag_filter(["屋外"], {"/fake/a.mp4", "/fake/b.mp4"})
        assert proxy._tag_filter_tags == ["屋外"]
        assert "/fake/a.mp4" in proxy._tag_filter_paths

    def test_clear_tag_filter(self):
        from file_manager.qt_models import FileSortFilterProxyModel
        proxy = FileSortFilterProxyModel()
        proxy.set_tag_filter(["屋外"], {"/fake/a.mp4"})
        proxy.set_tag_filter([], None)
        assert proxy._tag_filter_tags == []
        assert proxy._tag_filter_paths is None


# ---------------------------------------------------------------------------
# TagFilterPanel — UI (pytest-qt required)
# ---------------------------------------------------------------------------
class TestTagFilterPanel:
    def test_import(self):
        pytest.importorskip("pytestqt", reason="pytest-qt not installed")
        from file_manager.video_cluster_filter import TagFilterPanel  # noqa: F401

    def test_instantiate(self, qtbot):
        pytest.importorskip("pytestqt", reason="pytest-qt not installed")
        from file_manager.video_cluster_filter import TagFilterPanel
        panel = TagFilterPanel()
        qtbot.addWidget(panel)
        assert panel is not None

    def test_filter_changed_signal(self, qtbot, tmp_path):
        pytest.importorskip("pytestqt", reason="pytest-qt not installed")
        from file_manager.video_cluster_filter import TagFilterPanel
        from file_manager.video_cluster_db import VideoClusterDB
        db = VideoClusterDB(str(tmp_path / "db.db"))
        vid_id = db.upsert_video("/f.mp4", size=1, mtime=1.0, duration=1.0, width=1, height=1, fps=1.0)
        db.set_video_tag(vid_id, "テスト", category="scene", score=0.9, source="test", confirmed=False)

        panel = TagFilterPanel(db)
        qtbot.addWidget(panel)
        panel.refresh()

        emitted = []
        panel.filter_changed.connect(emitted.append)
        panel.clear_filter()
        assert emitted == [[]]
