from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

# 新しい OpenCV 向け: VideoCapture.open() 時に av_log_set_level を呼び出させる
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "8")  # AV_LOG_FATAL 以上のみ表示


@contextlib.contextmanager
def _suppress_ffmpeg_stderr():
    """FFmpeg が stderr に書き出す H.264/H.265 デコード警告を一時的に抑制する。

    os.dup2 で fd 2 (stderr) を /dev/null にリダイレクトし、C レベルの
    fprintf(stderr, ...) をキャプチャする。旧 OpenCV 向けのフォールバック。
    """
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        try:
            yield
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
    except OSError:
        yield  # os.dup2 が使えない環境ではそのまま続行

@dataclass
class VideoFeatures:
    """動画の特徴量情報"""
    
    path: str
    thumbnail_positions: List[float]  # サムネイル位置（0.0-1.0）
    frame_histograms: List[NDArray[np.float32]]  # 各フレームのヒストグラム
    frame_features: List[NDArray[np.float32]]  # 各フレームの特徴量
    average_color: NDArray[np.float32]  # 平均色
    duration: float
    resolution: Tuple[int, int]
    fps: float
    file_size: int

    @property
    def frame_count(self) -> int:
        """フレーム数を計算"""
        return int(self.duration * self.fps)

    def similarity_score(self, other: VideoFeatures) -> float:
        """他の動画との類似度を0.0-1.0で計算"""
        # 基本属性の重み
        duration_weight = 0.1
        resolution_weight = 0.1
        histogram_weight = 0.4
        feature_weight = 0.4
        
        # 長さの類似度（±10%以内を1.0とする）
        duration_diff = abs(self.duration - other.duration)
        duration_sim = max(0.0, 1.0 - duration_diff / max(self.duration, other.duration, 1.0))
        if duration_sim < 0.9:  # 長さが大きく異なる場合は類似度を0に
            return 0.0
            
        # 解像度の類似度
        w1, h1 = self.resolution
        w2, h2 = other.resolution
        resolution_sim = (min(w1, w2) * min(h1, h2)) / (max(w1, w2) * max(h1, h2))
        
        # ヒストグラムの類似度（サンプリング位置が近いもの同士で比較）
        hist_sims = []
        for i, hist1 in enumerate(self.frame_histograms):
            best_sim = 0.0
            for j, hist2 in enumerate(other.frame_histograms):
                pos_diff = abs(self.thumbnail_positions[i] - other.thumbnail_positions[j])
                if pos_diff > 0.1:  # 位置が離れすぎている場合はスキップ
                    continue
                sim = np.minimum(hist1, hist2).sum()
                best_sim = max(best_sim, sim)
            if best_sim > 0:
                hist_sims.append(best_sim)
        histogram_sim = np.mean(hist_sims) if hist_sims else 0.0
        
        # 特徴量の類似度
        feature_sims = []
        for i, feat1 in enumerate(self.frame_features):
            best_sim = 0.0
            for j, feat2 in enumerate(other.frame_features):
                pos_diff = abs(self.thumbnail_positions[i] - other.thumbnail_positions[j])
                if pos_diff > 0.1:
                    continue
                sim = np.dot(feat1, feat2) / (np.linalg.norm(feat1) * np.linalg.norm(feat2))
                best_sim = max(best_sim, sim)
            if best_sim > 0:
                feature_sims.append(best_sim)
        feature_sim = np.mean(feature_sims) if feature_sims else 0.0
        
        # 重み付き平均で総合的な類似度を計算
        similarity = (
            duration_weight * duration_sim +
            resolution_weight * resolution_sim +
            histogram_weight * histogram_sim +
            feature_weight * feature_sim
        )
        
        return float(similarity)

def compute_frame_features(frame: NDArray[np.uint8]) -> Tuple[NDArray[np.float32], NDArray[np.float32]]:
    """フレームからヒストグラムと特徴量を抽出"""
    # HSVヒストグラム
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    
    # エッジと色の特徴量
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    edge_features = cv2.resize(edges, (8, 8)).flatten() / 255.0
    
    color_features = cv2.resize(frame, (8, 8)).reshape(-1) / 255.0
    features = np.concatenate([edge_features, color_features])
    
    return hist.astype(np.float32), features.astype(np.float32)


def _calculate_positions(max_thumbnails: int) -> List[float]:
    """サムネイル抽出位置を 0.0-1.0 で返す。"""
    if max_thumbnails <= 1:
        return [0.5]
    step = 1.0 / (max_thumbnails + 1)
    return [step * (i + 1) for i in range(max_thumbnails)]


def _resize_to_thumbnail(
    frame: NDArray[np.uint8],
    thumbnail_size: tuple[int, int],
) -> NDArray[np.uint8]:
    """フレームを指定サムネイルサイズに収まるよう縮小する。"""
    target_width, target_height = thumbnail_size
    height, width = frame.shape[:2]
    if height <= 0 or width <= 0:
        return frame

    aspect_ratio = width / height
    resized_width = target_width
    resized_height = int(resized_width / aspect_ratio)
    if resized_height > target_height:
        resized_height = target_height
        resized_width = int(resized_height * aspect_ratio)

    resized_width = max(1, resized_width)
    resized_height = max(1, resized_height)
    return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)


def _calc_burst_interval(total_frames: int, max_thumbnails: int) -> int:
    """バーストフレームの間隔を動画長・キーフレーム数から自動計算する。

    キーフレーム間隔の約 1/3 を使い、広い時間範囲をカバーする。
    最小 3 フレーム、最大 120 フレームでクランプ。
    """
    key_spacing = total_frames // max(1, max_thumbnails + 1)
    return max(3, min(120, key_spacing // 3))


def extract_thumbnails_only(
    video_path: str | Path,
    max_thumbnails: int = 6,
    thumbnail_size: tuple[int, int] = (160, 90),
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Optional[list[tuple[float, NDArray[np.uint8]]]]:
    """サムネイル用フレームのみ抽出する。"""
    if not cv2 or not np:
        return None

    path = str(video_path)
    with _suppress_ffmpeg_stderr():
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return None

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                return None

            positions = _calculate_positions(max_thumbnails)
            results: list[tuple[float, NDArray[np.uint8]]] = []
            for index, position in enumerate(positions):
                frame_pos = int(position * total_frames)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                if ret:
                    results.append((position, _resize_to_thumbnail(frame, thumbnail_size)))
                if progress_callback:
                    progress_callback(int(((index + 1) / len(positions)) * 100))
            return results or None
        except Exception:
            return None
        finally:
            cap.release()

def extract_thumbnails_with_burst(
    video_path: str | Path,
    max_thumbnails: int = 6,
    thumbnail_size: tuple[int, int] = (160, 90),
    burst_count: int = 2,
    burst_interval_frames: Optional[int] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Optional[list[tuple[float, NDArray[np.uint8], list[tuple[int, NDArray[np.uint8]]]]]]:
    """各キーフレームとその前後バーストフレームを抽出する（高速版）。

    - CAP_PROP_POS_MSEC でキーフレーム境界へシークするため高速
    - cap.grab() でデコードせずにフレームをスキップするため高速
    - 各バーストウィンドウ内は前向き読み取りのみで余分なシークなし

    Returns:
        list of (position, key_frame, burst_list)
        burst_list: [(offset, frame), ...] offset < 0 = before, > 0 = after, offset 順にソート済み
    """
    if not cv2 or not np:
        return None

    path = str(video_path)
    with _suppress_ffmpeg_stderr():
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return None

    try:
        with _suppress_ffmpeg_stderr():
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        # フレーム番号 → ミリ秒変換係数
        ms_per_frame = 1000.0 / max(fps, 1e-9)

        interval = burst_interval_frames if burst_interval_frames is not None \
            else _calc_burst_interval(total_frames, max_thumbnails)

        positions = _calculate_positions(max_thumbnails)
        results: list[tuple[float, NDArray[np.uint8], list[tuple[int, NDArray[np.uint8]]]]] = []

        for step, position in enumerate(positions):
            key_no = int(position * total_frames)

            # このキーフレームに必要な全フレーム番号を収集（offset 0 = キー）
            needed: dict[int, int] = {key_no: 0}
            for offset in range(-burst_count, burst_count + 1):
                if offset == 0:
                    continue
                fn = max(0, min(total_frames - 1, key_no + offset * interval))
                needed[fn] = offset

            sorted_fns = sorted(needed.keys())

            collected: dict[int, NDArray[np.uint8]] = {}
            with _suppress_ffmpeg_stderr():
                # 先頭フレームへミリ秒でシーク（Iフレーム境界へ移動するため高速）
                cap.set(cv2.CAP_PROP_POS_MSEC, sorted_fns[0] * ms_per_frame)
                current = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                for target_fn in sorted_fns:
                    skip = target_fn - current
                    if skip < 0:
                        # キーフレーム丸め込みで行き過ぎた場合のみ再シーク
                        cap.set(cv2.CAP_PROP_POS_MSEC, target_fn * ms_per_frame)
                        current = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                        skip = target_fn - current

                    # デコードせずスキップ（grab のみ = 高速）
                    for _ in range(max(0, skip)):
                        cap.grab()
                    current = target_fn

                    ret, frame = cap.read()
                    current += 1
                    if ret:
                        collected[target_fn] = _resize_to_thumbnail(frame, thumbnail_size)

            if progress_callback:
                progress_callback(int((step + 1) / len(positions) * 100))

            if key_no not in collected:
                continue

            burst_list: list[tuple[int, NDArray[np.uint8]]] = [
                (offset, collected[fn])
                for fn, offset in needed.items()
                if offset != 0 and fn in collected
            ]
            burst_list.sort(key=lambda x: x[0])
            results.append((position, collected[key_no], burst_list))

        return results or None
    except Exception:
        return None
    finally:
        cap.release()


def extract_video_features(
    video_path: str | Path,
    max_thumbnails: int = 6,
    progress_callback: Optional[Callable[[int], None]] = None
) -> Optional[VideoFeatures]:
    """動画から特徴量を抽出"""
    if not cv2 or not np:  # OpenCV/NumPyが利用できない場合
        return None
        
    path = str(video_path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return None

    try:
        # 基本情報の取得
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = float(total_frames) / fps if fps > 0 else 0.0
        
        if total_frames == 0 or duration <= 0:
            return None
            
        # サムネイル位置の計算（0.0-1.0）
        positions = _calculate_positions(max_thumbnails)
            
        histograms = []
        features = []
        average_colors = []
        
        for i, pos in enumerate(positions):
            if progress_callback:
                progress = int((i / len(positions)) * 100)
                progress_callback(progress)
                
            frame_pos = int(pos * total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            
            if not ret:
                continue
                
            # ヒストグラムと特徴量の抽出
            hist, feat = compute_frame_features(frame)
            histograms.append(hist)
            features.append(feat)
            
            # 平均色の計算
            average_color = frame.mean(axis=(0, 1))
            average_colors.append(average_color)
            
        if not histograms:  # 1フレームも読めなかった場合
            return None
            
        # 全フレームの平均色
        average_color = np.mean(average_colors, axis=0).astype(np.float32)
        
        return VideoFeatures(
            path=path,
            thumbnail_positions=positions,
            frame_histograms=histograms,
            frame_features=features,
            average_color=average_color,
            duration=duration,
            resolution=(width, height),
            fps=fps,
            file_size=os.path.getsize(path)
        )
    
    except Exception:
        return None
    
    finally:
        cap.release()
