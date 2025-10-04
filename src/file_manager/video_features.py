from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

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
        if max_thumbnails == 1:
            positions = [0.5]
        else:
            step = 1.0 / (max_thumbnails + 1)
            positions = [step * (i + 1) for i in range(max_thumbnails)]
            
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