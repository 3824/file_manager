#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名の類似度による同一ファイル検出ロジック"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, List, Optional, Sequence

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
class SimilarFileGroup:
    """ファイル名の類似度に基づくグループ情報"""

    representative_name: str  # グループの代表ファイル名
    files: List[str]  # ファイルパスのリスト
    similarity_score: float  # グループ内の平均類似度
    file_sizes: dict[str, int] = None  # ファイルパスとサイズのマッピング

    def __post_init__(self) -> None:
        # 常にパスをソート済みに保つ
        self.files.sort()
        if self.file_sizes is None:
            self.file_sizes = {}

    def get_average_size(self) -> int:
        """グループ内のファイルの平均サイズを取得"""
        if not self.file_sizes:
            return 0
        return sum(self.file_sizes.values()) // len(self.file_sizes)

    def get_size_variance(self) -> float:
        """グループ内のファイルサイズの分散を計算"""
        if len(self.file_sizes) < 2:
            return 0.0
        avg = self.get_average_size()
        variance = sum((size - avg) ** 2 for size in self.file_sizes.values()) / len(self.file_sizes)
        return variance ** 0.5  # 標準偏差を返す


def normalize_filename(filename: str) -> str:
    """
    ファイル名を正規化して比較しやすくする

    - 数字のパディングを統一
    - 特殊文字を除去
    - 小文字に変換
    """
    # 拡張子を除去
    name_without_ext = Path(filename).stem

    # 小文字に変換
    normalized = name_without_ext.lower()

    # よくあるパターンの正規化
    # 例: "video_01", "video_1", "video-1" などを統一
    normalized = re.sub(r'[-_\s]+', '_', normalized)

    # 括弧内の情報を除去（コピーなどの表記）
    normalized = re.sub(r'\([^)]*\)', '', normalized)
    normalized = re.sub(r'\[[^\]]*\]', '', normalized)

    # 連続するアンダースコアを1つに
    normalized = re.sub(r'_+', '_', normalized)

    # 前後の空白・アンダースコアを削除
    normalized = normalized.strip('_').strip()

    return normalized


def calculate_similarity(name1: str, name2: str) -> float:
    """
    2つのファイル名の類似度を計算（0.0-1.0）

    SequenceMatcherを使用して編集距離ベースの類似度を計算
    """
    norm1 = normalize_filename(name1)
    norm2 = normalize_filename(name2)

    if not norm1 or not norm2:
        return 0.0

    # SequenceMatcherで類似度を計算
    matcher = SequenceMatcher(None, norm1, norm2)
    return matcher.ratio()


def calculate_size_similarity(size1: int, size2: int) -> float:
    """
    2つのファイルサイズの類似度を計算（0.0-1.0）

    サイズの差が小さいほど類似度が高い
    """
    if size1 == 0 and size2 == 0:
        return 1.0
    if size1 == 0 or size2 == 0:
        return 0.0

    # サイズの差の割合を計算
    larger = max(size1, size2)
    smaller = min(size1, size2)
    ratio = smaller / larger

    return ratio


def calculate_combined_similarity(
    name1: str,
    name2: str,
    size1: int,
    size2: int,
    name_weight: float = 0.7,
    size_weight: float = 0.3,
) -> float:
    """
    ファイル名とサイズを組み合わせた類似度を計算

    Args:
        name1: ファイル名1
        name2: ファイル名2
        size1: ファイルサイズ1（バイト）
        size2: ファイルサイズ2（バイト）
        name_weight: ファイル名の重み（デフォルト: 0.7）
        size_weight: サイズの重み（デフォルト: 0.3）

    Returns:
        0.0-1.0 の類似度スコア
    """
    name_sim = calculate_similarity(name1, name2)
    size_sim = calculate_size_similarity(size1, size2)

    return name_sim * name_weight + size_sim * size_weight


def extract_number_pattern(filename: str) -> tuple[str, list[int]]:
    """
    ファイル名からパターンと数字部分を抽出

    例: "video_001.mp4" -> ("video_", [1])
        "test_2024_01.avi" -> ("test__", [2024, 1])
    """
    name_without_ext = Path(filename).stem
    normalized = normalize_filename(name_without_ext)

    # 数字を抽出
    numbers = [int(n) for n in re.findall(r'\d+', normalized)]

    # 数字部分をプレースホルダーに置き換えてパターンを作成
    pattern = re.sub(r'\d+', '#', normalized)

    return pattern, numbers


def is_video_file(path: Path, extensions: Sequence[str] | None = None) -> bool:
    """動画拡張子かどうかを判定"""
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    target_exts = tuple(e.lower() for e in (extensions or DEFAULT_VIDEO_EXTENSIONS))
    return suffix in target_exts


def find_similar_filenames(
    base_path: str | os.PathLike[str],
    *,
    recursive: bool = False,
    extensions: Sequence[str] | None = None,
    similarity_threshold: float = 0.7,
    min_group_size: int = 2,
    use_file_size: bool = True,
    size_weight: float = 0.3,
    progress_callback: ProgressCallback = None,
    stop_callback: StopCallback = None,
) -> List[SimilarFileGroup]:
    """
    指定フォルダ内のファイル名が類似しているファイルをグループ化

    Args:
        base_path: 検索対象のディレクトリパス
        recursive: サブディレクトリも検索するかどうか
        extensions: 検索対象の拡張子リスト（Noneの場合は動画ファイルのみ）
        similarity_threshold: 類似度のしきい値（0.0-1.0）
        min_group_size: グループとして扱う最小ファイル数
        use_file_size: ファイルサイズも考慮するかどうか
        size_weight: サイズの重み（use_file_size=Trueの場合のみ有効）
        progress_callback: 進捗コールバック（0-100）
        stop_callback: 中断チェックコールバック

    Returns:
        List[SimilarFileGroup]: 類似ファイルグループのリスト
    """
    base_dir = Path(base_path)

    if progress_callback:
        progress_callback(0)

    if stop_callback and stop_callback():
        return []

    if not base_dir.exists() or not base_dir.is_dir():
        if progress_callback:
            progress_callback(100)
        return []

    # ファイル一覧の収集
    files: List[Path] = []
    iterator = base_dir.rglob("*") if recursive else base_dir.iterdir()

    for path in iterator:
        if stop_callback and stop_callback():
            if progress_callback:
                progress_callback(100)
            return []

        # 動画ファイルのみを対象とする場合
        if extensions is None:
            if is_video_file(path):
                files.append(path)
        # 指定された拡張子のファイルを対象とする場合
        elif path.is_file() and path.suffix.lower() in [e.lower() for e in extensions]:
            files.append(path)
        # 拡張子指定なし（空リスト）の場合は全ファイル
        elif extensions == [] and path.is_file():
            files.append(path)

    if not files:
        if progress_callback:
            progress_callback(100)
        return []

    if progress_callback:
        progress_callback(10)

    # パターンベースの初期グルーピング
    pattern_groups: dict[str, List[Path]] = {}
    for file_path in files:
        pattern, numbers = extract_number_pattern(file_path.name)
        pattern_groups.setdefault(pattern, []).append(file_path)

    if progress_callback:
        progress_callback(30)

    # ファイルサイズを取得
    file_sizes: dict[str, int] = {}
    for file_path in files:
        try:
            file_sizes[str(file_path)] = file_path.stat().st_size
        except OSError:
            file_sizes[str(file_path)] = 0

    # 類似度ベースのグルーピング
    similar_groups: List[SimilarFileGroup] = []
    processed_files: set[str] = set()
    total_files = len(files)
    current_progress = 30

    for i, file1 in enumerate(files):
        if stop_callback and stop_callback():
            return similar_groups

        file1_str = str(file1)
        if file1_str in processed_files:
            continue

        # このファイルと類似しているファイルを探す
        similar_files = [file1_str]
        similar_file_sizes = {file1_str: file_sizes.get(file1_str, 0)}

        for file2 in files[i + 1:]:
            file2_str = str(file2)
            if file2_str in processed_files:
                continue

            # 類似度を計算
            if use_file_size:
                similarity = calculate_combined_similarity(
                    file1.name,
                    file2.name,
                    file_sizes.get(file1_str, 0),
                    file_sizes.get(file2_str, 0),
                    name_weight=1.0 - size_weight,
                    size_weight=size_weight,
                )
            else:
                similarity = calculate_similarity(file1.name, file2.name)

            if similarity >= similarity_threshold:
                similar_files.append(file2_str)
                similar_file_sizes[file2_str] = file_sizes.get(file2_str, 0)
                processed_files.add(file2_str)

        # 最小グループサイズ以上の場合のみグループとして追加
        if len(similar_files) >= min_group_size:
            # グループ内の平均類似度を計算
            total_similarity = 0.0
            comparison_count = 0

            for j, f1 in enumerate(similar_files):
                for f2 in similar_files[j + 1:]:
                    if use_file_size:
                        sim = calculate_combined_similarity(
                            Path(f1).name,
                            Path(f2).name,
                            file_sizes.get(f1, 0),
                            file_sizes.get(f2, 0),
                            name_weight=1.0 - size_weight,
                            size_weight=size_weight,
                        )
                    else:
                        sim = calculate_similarity(Path(f1).name, Path(f2).name)
                    total_similarity += sim
                    comparison_count += 1

            avg_similarity = total_similarity / comparison_count if comparison_count > 0 else 1.0

            # 代表ファイル名は最初のファイル
            representative_name = Path(similar_files[0]).name

            similar_groups.append(
                SimilarFileGroup(
                    representative_name=representative_name,
                    files=similar_files,
                    similarity_score=avg_similarity,
                    file_sizes=similar_file_sizes,
                )
            )
            processed_files.add(file1_str)

        # 進捗更新
        current_progress = 30 + int((i / total_files) * 70)
        if progress_callback:
            progress_callback(min(current_progress, 100))

    # 類似度の高い順にソート
    similar_groups.sort(key=lambda g: (-g.similarity_score, -len(g.files)))

    if progress_callback:
        progress_callback(100)

    return similar_groups
