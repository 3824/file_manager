#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動画ファイルの重複検出ロジック"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set

from .video_features import VideoFeatures

ProgressCallback = Optional[Callable[[int], None]]
StopCallback = Optional[Callable[[], bool]]

DEFAULT_VIDEO_EXTENSIONS: Sequence[str] = (
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".3gp",
    ".mpg",
    ".mpeg",
    ".mts",
    ".m2ts",
)


@dataclass
class DuplicateGroup:
    """同一と推定される動画ファイルのグループ情報"""

    size: int
    sha256: str
    files: List[str]
    features: Dict[str, Optional[VideoFeatures]] = field(default_factory=dict)
    similarity_threshold: float = 0.95

    def __post_init__(self) -> None:
        # 常にパスをソート済みに保つ
        self.files.sort()

    def add_file_with_features(self, file_path: str, features: Optional[VideoFeatures]) -> None:
        """ファイルを特徴量と共に追加"""
        if file_path not in self.files:
            self.files.append(file_path)
            self.files.sort()
        self.features[file_path] = features

    def is_similar(self, file_path: str, features: Optional[VideoFeatures]) -> bool:
        """特徴量ベースの類似度を計算"""
        if not features:
            return False

        # すでにグループにある動画との類似度を確認
        for existing_path, existing_features in self.features.items():
            if not existing_features:
                continue
            
            sim = features.similarity_score(existing_features)
            if sim >= self.similarity_threshold:
                return True
                
        return False

    def calculate_group_similarity(self) -> float:
        """グループ内の動画の平均類似度を計算"""
        if len(self.files) < 2:
            return 1.0

        valid_features = [f for f in self.features.values() if f is not None]
        if len(valid_features) < 2:
            return 0.0

        total_sim = 0.0
        count = 0
        for i, feat1 in enumerate(valid_features):
            for feat2 in valid_features[i + 1:]:
                sim = feat1.similarity_score(feat2)
                total_sim += sim
                count += 1

        return total_sim / count if count > 0 else 0.0


def is_video_file(path: Path, extensions: Sequence[str] | None = None) -> bool:
    """動画拡張子かどうかを判定"""
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    target_exts = tuple(e.lower() for e in (extensions or DEFAULT_VIDEO_EXTENSIONS))
    return suffix in target_exts


def hash_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """ファイル全体のSHA-256ハッシュを計算"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _to_report_path(path: Path) -> str:
    """Return an absolute path string without resolving symlinks when possible."""
    try:
        return str(path if path.is_absolute() else path.absolute())
    except OSError:
        return str(path)


def find_duplicate_videos_with_features(
    base_path: str | os.PathLike[str],
    *,
    recursive: bool = True,
    extensions: Sequence[str] | None = None,
    progress_callback: ProgressCallback = None,
    stop_callback: StopCallback = None,
    features_callback: Optional[Callable[[str], Optional[VideoFeatures]]] = None,
    similarity_threshold: float = 0.95,
    size_threshold_mb: int = 10,
) -> List[DuplicateGroup]:
    """
    指定フォルダ配下の動画ファイルを走査し、同一と推定されるグループを返す。
    特徴量ベースの類似度も考慮して検索を高速化します。

    Args:
        base_path: 検索対象のディレクトリパス
        recursive: サブディレクトリも検索するかどうか
        extensions: 検索対象の拡張子リスト
        progress_callback: 進捗コールバック（0-100）
        stop_callback: 中断チェックコールバック
        features_callback: 特徴量抽出コールバック
        similarity_threshold: 類似度のしきい値（0.0-1.0）
        size_threshold_mb: ファイルサイズのしきい値（MB）

    Returns:
        List[DuplicateGroup]: 重複グループのリスト

    進捗コールバックには 0-100 の整数値が渡されます。
    中断コールバックが真を返した場合は即座に処理を中断します。
    """
    base_dir = Path(base_path)
    if progress_callback:
        progress_callback(0)

    if stop_callback and stop_callback():
        if progress_callback:
            progress_callback(100)
        return []

    if not base_dir.exists() or not base_dir.is_dir():
        if progress_callback:
            progress_callback(100)
        return []

    # ファイル一覧の収集（動画ファイルのみ）
    video_files = []
    for path in (base_dir.rglob("*") if recursive else base_dir.iterdir()):
        if stop_callback and stop_callback():
            if progress_callback:
                progress_callback(100)
            return []

        if not is_video_file(path, extensions):
            continue

        try:
            size = path.stat().st_size
            if size < size_threshold_mb * 1024 * 1024:  # 小さすぎるファイルは除外
                continue
            video_files.append((path, size))
        except OSError:
            continue

    # サイズでグループ化（最初の高速フィルタリング）
    size_groups: Dict[int, List[Path]] = {}
    for path, size in video_files:
        size_groups.setdefault(size, []).append(path)

    # 結果のグループを格納
    duplicate_groups = []
    total_files = len(video_files)
    processed_files = 0

    # サイズ順に処理（大きいファイルから）
    size_groups_list = sorted(size_groups.items(), key=lambda x: x[0], reverse=True)
    for file_size, path_list in size_groups_list:
        # 同じサイズのファイルが1つしかない場合はスキップ
        if len(path_list) < 2:
            continue

        # 同じサイズのファイルはハッシュ値を計算して比較
        hash_groups: Dict[str, DuplicateGroup] = {}
        for path in path_list:
            try:
                file_hash = hash_file(path)
                str_path = _to_report_path(path)

                # 特徴量の抽出
                features = None
                if features_callback:
                    features = features_callback(str_path)

                # ハッシュ値が同じ場合は同一グループに追加
                if file_hash in hash_groups:
                    hash_groups[file_hash].add_file_with_features(str_path, features)
                else:
                    group = DuplicateGroup(file_size, file_hash, [str_path],
                                         similarity_threshold=similarity_threshold)
                    if features:
                        group.features[str_path] = features
                    hash_groups[file_hash] = group

            except OSError:
                continue

            # 進捗の更新
            processed_files += 1
            if progress_callback:
                progress = int((processed_files / total_files) * 100)
                progress_callback(min(progress, 100))

            if stop_callback and stop_callback():
                return [g for g in hash_groups.values() if len(g.files) > 1]

        # 類似度の高いグループを結合
        if features_callback:
            groups_to_merge = list(hash_groups.values())
            i = 0
            while i < len(groups_to_merge):
                j = i + 1
                while j < len(groups_to_merge):
                    group1 = groups_to_merge[i]
                    group2 = groups_to_merge[j]
                    
                    # サイズの差が大きい場合はスキップ
                    if abs(group1.size - group2.size) / max(group1.size, group2.size) > 0.1:
                        j += 1
                        continue
                    
                    # 互いのグループ内の動画の特徴量を比較
                    merge = False
                    for file1, features1 in group1.features.items():
                        for file2, features2 in group2.features.items():
                            if features1 and features2:
                                sim = features1.similarity_score(features2)
                                if sim >= similarity_threshold:
                                    merge = True
                                    break
                        if merge:
                            break
                            
                    if merge:
                        # グループを結合
                        for file_path, features in group2.features.items():
                            group1.add_file_with_features(file_path, features)
                        groups_to_merge.pop(j)
                    else:
                        j += 1
                i += 1
                
            # 結果に追加（2ファイル以上のグループのみ）
            duplicate_groups.extend([g for g in groups_to_merge if len(g.files) > 1])
        else:
            # 特徴量が利用できない場合は、ハッシュベースの結果をそのまま追加
            duplicate_groups.extend([g for g in hash_groups.values() if len(g.files) > 1])

    if progress_callback:
        progress_callback(100)

    return duplicate_groups


def find_duplicate_videos(
    base_path: str | os.PathLike[str],
    *,
    recursive: bool = True,
    extensions: Sequence[str] | None = None,
    progress_callback: ProgressCallback = None,
    stop_callback: StopCallback = None,
) -> List[DuplicateGroup]:
    """Find duplicate video files without optional feature extraction."""
    base_dir = Path(base_path)
    if progress_callback:
        progress_callback(0)

    if stop_callback and stop_callback():
        if progress_callback:
            progress_callback(100)
        return []

    if not base_dir.exists() or not base_dir.is_dir():
        if progress_callback:
            progress_callback(100)
        return []

    video_extensions = tuple(e.lower() for e in (extensions or DEFAULT_VIDEO_EXTENSIONS))

    video_files: List[Path] = []
    iterator: Iterable[Path]
    if recursive:
        iterator = (p for p in base_dir.rglob("*") if p.is_file())
    else:
        iterator = (p for p in base_dir.iterdir() if p.is_file())

    for candidate in iterator:
        if stop_callback and stop_callback():
            if progress_callback:
                progress_callback(100)
            return []
        if candidate.suffix.lower() in video_extensions:
            video_files.append(candidate)

    total_files = len(video_files)
    if total_files == 0:
        if progress_callback:
            progress_callback(100)
        return []

    if progress_callback:
        progress_callback(5)

    by_size: Dict[int, List[Path]] = {}
    for index, path in enumerate(video_files, start=1):
        if stop_callback and stop_callback():
            if progress_callback:
                progress_callback(100)
            return []
        try:
            size = path.stat().st_size
        except OSError:
            continue
        by_size.setdefault(size, []).append(path)
        if progress_callback:
            progress = 5 + int((index / total_files) * 35)
            progress_callback(min(progress, 40))

    candidate_groups = [(size, paths) for size, paths in by_size.items() if len(paths) > 1]
    if not candidate_groups:
        if progress_callback:
            progress_callback(100)
        return []

    total_hash_targets = sum(len(paths) for _, paths in candidate_groups)
    if total_hash_targets == 0:
        if progress_callback:
            progress_callback(100)
        return []

    duplicates: List[DuplicateGroup] = []
    hashed_count = 0

    for size, paths in sorted(candidate_groups, key=lambda item: item[0]):
        if stop_callback and stop_callback():
            if progress_callback:
                progress_callback(100)
            return duplicates
        by_hash: Dict[str, List[Path]] = {}
        for path in sorted(paths):
            if stop_callback and stop_callback():
                if progress_callback:
                    progress_callback(100)
                return duplicates
            try:
                digest = hash_file(path)
            except OSError:
                hashed_count += 1
                continue
            by_hash.setdefault(digest, []).append(path)
            hashed_count += 1
            if progress_callback:
                progress = 40 + int((hashed_count / total_hash_targets) * 59)
                progress_callback(min(progress, 99))

        for digest, dup_paths in by_hash.items():
            if len(dup_paths) > 1:
                duplicates.append(
                    DuplicateGroup(
                        size=size,
                        sha256=digest,
                        files=[_to_report_path(p) for p in dup_paths],
                    )
                )

    duplicates.sort(key=lambda group: (group.size, group.sha256, group.files[0]))

    if progress_callback:
        progress_callback(100)

    return duplicates


