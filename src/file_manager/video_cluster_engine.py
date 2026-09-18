"""動画クラスタリングエンジン。

埋め込み生成・タグ付け・クラスタリングを担う。
依存ライブラリ (open_clip, sklearn) はオプション。未インストールでも
ColorHistogram フォールバックで最低限動作する。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    pass

# -------------------------------------------------------------------------
# オプション依存インポート
# -------------------------------------------------------------------------
try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    import open_clip
    _OPEN_CLIP_AVAILABLE = True
except ImportError:
    _OPEN_CLIP_AVAILABLE = False

try:
    from transformers import AutoProcessor, AutoModel
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import normalize as sk_normalize
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

# -------------------------------------------------------------------------
# デフォルトタグ語彙
# -------------------------------------------------------------------------
DEFAULT_TAG_VOCAB: dict[str, list[str]] = {
    "scene": [
        "屋外", "屋内", "自然", "都市", "夜景", "海", "山", "空",
        "部屋", "キッチン", "オフィス", "道路",
    ],
    "subject": [
        "人物", "動物", "食べ物", "車", "建物", "植物", "テキスト",
        "画面", "製品",
    ],
    "genre": [
        "ゲーム実況", "アニメ", "映画", "スライド", "会議", "料理",
        "旅行", "スポーツ", "音楽", "教育", "ニュース",
    ],
    "quality": [
        "明るい", "暗い", "カラフル", "モノクロ", "ぼやけている",
    ],
}

# 英語プロンプトテンプレート（CLIP 系モデルとの互換用）
_TAG_PROMPT_MAP: dict[str, str] = {
    "屋外": "a photo of outdoors",
    "屋内": "a photo of indoors",
    "自然": "a photo of nature landscape",
    "都市": "a photo of city street",
    "夜景": "a photo of night scene",
    "海": "a photo of the sea or ocean",
    "山": "a photo of mountains",
    "空": "a photo of the sky",
    "部屋": "a photo of a room interior",
    "キッチン": "a photo of kitchen",
    "オフィス": "a photo of office",
    "道路": "a photo of road or highway",
    "人物": "a photo of a person",
    "動物": "a photo of an animal",
    "食べ物": "a photo of food",
    "車": "a photo of a car",
    "建物": "a photo of a building",
    "植物": "a photo of plants",
    "テキスト": "a screenshot with text",
    "画面": "a screenshot of computer screen",
    "製品": "a photo of a product",
    "ゲーム実況": "a screenshot of a video game",
    "アニメ": "an anime illustration",
    "映画": "a movie scene",
    "スライド": "a presentation slide",
    "会議": "a video conference meeting",
    "料理": "a cooking video",
    "旅行": "a travel video",
    "スポーツ": "a sports video",
    "音楽": "a music video",
    "教育": "an educational lecture",
    "ニュース": "a news broadcast",
    "明るい": "a bright well-lit scene",
    "暗い": "a dark low-light scene",
    "カラフル": "a colorful vivid scene",
    "モノクロ": "a black and white scene",
    "ぼやけている": "a blurry out-of-focus scene",
}


# -------------------------------------------------------------------------
# ベクトル変換ユーティリティ
# -------------------------------------------------------------------------
def vec_to_bytes(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()

def bytes_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32).copy()

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# =========================================================================
# 埋め込みバックエンド
# =========================================================================
class EmbeddingBackend:
    """埋め込みバックエンドの基底クラス。"""

    name: str = "base"
    dim: int = 64

    def encode_frames(self, frames: list[np.ndarray]) -> np.ndarray:
        """フレーム画像リスト → (N, dim) numpy 配列。"""
        raise NotImplementedError

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        """テキストリスト → (N, dim) numpy 配列。Zero-shot 用。"""
        raise NotImplementedError

    def supports_text(self) -> bool:
        return False


class ColorHistogramBackend(EmbeddingBackend):
    """cv2 の HSV カラーヒストグラム + エッジ特徴ベースのフォールバック。

    外部 ML ライブラリ不要。精度は低いが、インストールコストゼロ。
    """

    name = "color_hist_v1"
    dim = 128

    def encode_frames(self, frames: list[np.ndarray]) -> np.ndarray:
        vecs = []
        for frame in frames:
            vecs.append(self._frame_vec(frame))
        return np.stack(vecs, axis=0) if vecs else np.zeros((0, self.dim), dtype=np.float32)

    def _frame_vec(self, frame: np.ndarray) -> np.ndarray:
        if not _CV2_AVAILABLE:
            return np.zeros(self.dim, dtype=np.float32)
        # HSV ヒストグラム (H: 8, S: 8 → 64 bin)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist_hs = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
        hist_hs = cv2.normalize(hist_hs, hist_hs).flatten().astype(np.float32)  # 64

        # エッジ密度 + 明るさ特徴 (64 → 合計 128)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
        brightness = small.flatten() / 255.0  # 64

        vec = np.concatenate([hist_hs, brightness.astype(np.float32)])
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        return vec

    def supports_text(self) -> bool:
        return False


class OpenCLIPBackend(EmbeddingBackend):
    """open_clip を使った CLIP/SigLIP 2 バックエンド。"""

    name = "open_clip_v1"
    dim = 768

    def __init__(
        self,
        model_name: str = "ViT-B-16-SigLIP2",
        pretrained: str = "webli",
        device: Optional[str] = None,
    ):
        if not _OPEN_CLIP_AVAILABLE or not _TORCH_AVAILABLE:
            raise ImportError("open_clip と torch が必要です")
        import torch as _torch
        self._device = device or ("cuda" if _torch.cuda.is_available() else "cpu")
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=self._device
        )
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer(model_name)
        # 出力次元を実際に取得
        with _torch.no_grad():
            dummy = _torch.zeros(1, 3, 224, 224, device=self._device)
            feat = self._model.encode_image(dummy)
        self.dim = int(feat.shape[-1])
        self.name = f"open_clip_{model_name}"

    def encode_frames(self, frames: list[np.ndarray]) -> np.ndarray:
        import torch as _torch
        from PIL import Image as _Image
        imgs = []
        for f in frames:
            rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB) if _CV2_AVAILABLE else f
            pil = _Image.fromarray(rgb)
            imgs.append(self._preprocess(pil))
        batch = _torch.stack(imgs).to(self._device)
        with _torch.no_grad():
            feats = self._model.encode_image(batch).cpu().numpy()
        norms = np.linalg.norm(feats, axis=1, keepdims=True)
        norms = np.where(norms < 1e-9, 1.0, norms)
        return (feats / norms).astype(np.float32)

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        import torch as _torch
        tokens = self._tokenizer(texts).to(self._device)
        with _torch.no_grad():
            feats = self._model.encode_text(tokens).cpu().numpy()
        norms = np.linalg.norm(feats, axis=1, keepdims=True)
        norms = np.where(norms < 1e-9, 1.0, norms)
        return (feats / norms).astype(np.float32)

    def supports_text(self) -> bool:
        return True


def build_backend(prefer: str = "auto") -> EmbeddingBackend:
    """利用可能な最良バックエンドを生成する。"""
    if prefer in ("auto", "open_clip") and _OPEN_CLIP_AVAILABLE and _TORCH_AVAILABLE:
        try:
            return OpenCLIPBackend()
        except Exception:
            pass
    return ColorHistogramBackend()


# =========================================================================
# タグエンジン
# =========================================================================
class ZeroShotTagger:
    """コサイン類似度ベースの Zero-shot マルチラベルタグ付け。

    CLIP 系バックエンドは encode_texts でタグベクトルを先にキャッシュする。
    ColorHistogram バックエンドでは軽量ルールベースにフォールバックする。
    """

    def __init__(
        self,
        backend: EmbeddingBackend,
        vocab: Optional[dict[str, list[str]]] = None,
        score_threshold: float = 0.22,
        top_k_per_category: int = 3,
        min_frame_ratio: float = 0.25,
    ):
        self._backend = backend
        self._vocab = vocab or DEFAULT_TAG_VOCAB
        self._thr = score_threshold
        self._top_k = top_k_per_category
        self._min_frame_ratio = min_frame_ratio
        self._tag_vecs: Optional[dict[str, np.ndarray]] = None
        self._flat_tags: list[str] = []
        self._flat_cats: list[str] = []

        if self._backend is not None and self._backend.supports_text():
            self._precompute_tag_vecs()

    def _precompute_tag_vecs(self) -> None:
        all_tags: list[str] = []
        all_cats: list[str] = []
        all_prompts: list[str] = []
        for cat, tags in self._vocab.items():
            for tag in tags:
                prompt = _TAG_PROMPT_MAP.get(tag, f"a photo of {tag}")
                all_tags.append(tag)
                all_cats.append(cat)
                all_prompts.append(prompt)
        vecs = self._backend.encode_texts(all_prompts)
        self._tag_vecs = {}
        for i, tag in enumerate(all_tags):
            self._tag_vecs[tag] = vecs[i]
        self._flat_tags = all_tags
        self._flat_cats = all_cats

    def tag_frames(self, frame_vecs: np.ndarray) -> list[dict[str, float]]:
        """フレームごとにタグスコアを計算して返す。CLIP バックエンド専用。"""
        if self._tag_vecs is None:
            return []
        n = len(frame_vecs)
        results: list[dict[str, float]] = []
        for fv in frame_vecs:
            scores: dict[str, float] = {}
            for tag, tv in self._tag_vecs.items():
                scores[tag] = cosine_sim(fv, tv)
            results.append(scores)
        return results

    def aggregate_tags(
        self, frame_scores: list[dict[str, float]]
    ) -> list[tuple[str, str, float]]:
        """フレームスコアを動画レベルに集約してタグリストを返す。

        Returns:
            List of (canonical_tag, category, score)
        """
        if not frame_scores:
            return []
        n = len(frame_scores)
        # タグごとに出現フレーム数を数える
        tag_frame_count: dict[str, int] = {}
        tag_total_score: dict[str, float] = {}
        for fs in frame_scores:
            for tag, sc in fs.items():
                if sc >= self._thr:
                    tag_frame_count[tag] = tag_frame_count.get(tag, 0) + 1
                    tag_total_score[tag] = tag_total_score.get(tag, 0.0) + sc
        # フレーム比率 >= min_frame_ratio のタグを採用
        result: list[tuple[str, str, float]] = []
        cat_map = {t: c for c, tags in self._vocab.items() for t in tags}
        for tag, cnt in tag_frame_count.items():
            ratio = cnt / n
            if ratio >= self._min_frame_ratio:
                avg_score = tag_total_score[tag] / cnt
                cat = cat_map.get(tag, "general")
                result.append((tag, cat, avg_score))
        # スコア降順ソート
        result.sort(key=lambda x: -x[2])
        return result

    def tag_frames_heuristic(self, frames: list[np.ndarray]) -> list[tuple[str, str, float]]:
        """ColorHistogram バックエンド用のルールベースタグ付け。"""
        if not _CV2_AVAILABLE or not frames:
            return []
        brightness_list: list[float] = []
        sat_list: list[float] = []
        edge_list: list[float] = []
        for frame in frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            brightness_list.append(float(hsv[:, :, 2].mean()) / 255.0)
            sat_list.append(float(hsv[:, :, 1].mean()) / 255.0)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            edge_list.append(float(edges.mean()) / 255.0)

        avg_b = float(np.mean(brightness_list))
        avg_s = float(np.mean(sat_list))
        avg_e = float(np.mean(edge_list))

        result: list[tuple[str, str, float]] = []
        if avg_b < 0.3:
            result.append(("暗い", "quality", 0.8))
            result.append(("夜景", "scene", 0.5))
        elif avg_b > 0.7:
            result.append(("明るい", "quality", 0.8))
        if avg_s > 0.4:
            result.append(("カラフル", "quality", 0.6))
        if avg_s < 0.05:
            result.append(("モノクロ", "quality", 0.7))
        if avg_e > 0.05:
            result.append(("テキスト", "subject", 0.4))
        return result

    def get_tags(
        self, frames: list[np.ndarray], frame_vecs: Optional[np.ndarray] = None
    ) -> list[tuple[str, str, float]]:
        """フレーム画像からタグを生成する。CLIP 対応時は Zero-shot、非対応はヒューリスティック。"""
        if self._backend is not None and self._backend.supports_text() and frame_vecs is not None and len(frame_vecs) > 0:
            per_frame = self.tag_frames(frame_vecs)
            return self.aggregate_tags(per_frame)
        return self.tag_frames_heuristic(frames)


# =========================================================================
# クラスタリングエンジン
# =========================================================================
class ClusterEngine:
    """K-Means ベースの動画クラスタリング。

    sklearn が未インストールの場合は簡易実装（ランダム初期化 K-Means）を使用。
    """

    CLUSTER_COLORS = [
        "#6200EE", "#03DAC6", "#FF6D00", "#0091EA", "#64DD17",
        "#FFD600", "#AA00FF", "#C51162", "#2962FF", "#00BFA5",
        "#FF6F00", "#1B5E20",
    ]

    def __init__(self, n_clusters: int = 8, random_state: int = 42):
        self._n_clusters = n_clusters
        self._random_state = random_state

    def cluster(self, video_ids: list[int], embeddings: np.ndarray) -> list[tuple[int, int, float]]:
        """クラスタリングを実行して (video_id, cluster_label, prob) リストを返す。"""
        if len(video_ids) == 0:
            return []
        n = len(video_ids)
        k = min(self._n_clusters, n)
        labels = self._run_kmeans(embeddings, k)
        return [(vid, int(lbl), 1.0) for vid, lbl in zip(video_ids, labels)]

    def _run_kmeans(self, X: np.ndarray, k: int) -> np.ndarray:
        if _SKLEARN_AVAILABLE:
            km = KMeans(n_clusters=k, random_state=self._random_state, n_init="auto")
            return km.fit_predict(X).astype(int)
        # 簡易 K-Means（sklearn 非依存）
        return self._simple_kmeans(X, k)

    def _simple_kmeans(self, X: np.ndarray, k: int, max_iter: int = 50) -> np.ndarray:
        rng = np.random.default_rng(self._random_state)
        idx = rng.choice(len(X), k, replace=False)
        centers = X[idx].copy()
        labels = np.zeros(len(X), dtype=int)
        for _ in range(max_iter):
            # 各点を最近傍センターに割当
            dists = np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1)
            new_labels = dists.argmin(axis=1)
            if np.all(new_labels == labels):
                break
            labels = new_labels
            for i in range(k):
                members = X[labels == i]
                if len(members) > 0:
                    centers[i] = members.mean(axis=0)
        return labels

    def auto_name_cluster(self, cluster_id: int, tags: list[str]) -> str:
        """クラスタを代表タグで命名する。"""
        if tags:
            return " / ".join(tags[:3])
        return f"クラスタ {cluster_id + 1}"
