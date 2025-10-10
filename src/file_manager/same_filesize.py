#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同じファイルサイズのファイルを検出する機能"""

from __future__ import annotations

import os
import stat
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class FileInfo:
    """ファイル情報"""
    path: str
    size: int
    attributes: str


@dataclass
class SameFileSizeGroup:
    """同じファイルサイズのファイルグループ"""
    size: int
    files: List[FileInfo]

    def __len__(self) -> int:
        return len(self.files)


def get_file_attributes(filepath: Path) -> str:
    """
    ファイルの属性を取得して文字列で返す

    Args:
        filepath: ファイルパス

    Returns:
        属性を表す文字列（例: "R" = 読み込み専用, "H" = 隠しファイル）
    """
    attributes = []

    try:
        file_stat = filepath.stat()
        mode = file_stat.st_mode

        if sys.platform == "win32":
            # Windows の場合
            import ctypes
            FILE_ATTRIBUTE_READONLY = 0x01
            FILE_ATTRIBUTE_HIDDEN = 0x02
            FILE_ATTRIBUTE_SYSTEM = 0x04
            FILE_ATTRIBUTE_ARCHIVE = 0x20

            try:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
                if attrs != -1:
                    if attrs & FILE_ATTRIBUTE_READONLY:
                        attributes.append("R")
                    if attrs & FILE_ATTRIBUTE_HIDDEN:
                        attributes.append("H")
                    if attrs & FILE_ATTRIBUTE_SYSTEM:
                        attributes.append("S")
                    if attrs & FILE_ATTRIBUTE_ARCHIVE:
                        attributes.append("A")
            except Exception:
                pass
        else:
            # Unix系の場合
            if not (mode & stat.S_IWUSR):
                attributes.append("R")  # 読み込み専用（書き込み不可）
            if filepath.name.startswith('.'):
                attributes.append("H")  # 隠しファイル
            if mode & stat.S_IXUSR:
                attributes.append("X")  # 実行可能

        # 追加の共通属性
        if mode & stat.S_IRUSR:
            if "R" not in attributes:
                attributes.append("r")  # 読み取り可能（小文字）

    except (OSError, PermissionError):
        attributes.append("?")  # アクセスできない

    return "".join(attributes) if attributes else "-"


def find_same_filesize_files(
    directory: str | Path,
    min_group_size: int = 2
) -> List[SameFileSizeGroup]:
    """
    指定されたディレクトリ内で同じファイルサイズのファイルを検出する

    Args:
        directory: 検索対象のディレクトリパス
        min_group_size: グループと見なす最小ファイル数（デフォルト: 2）

    Returns:
        同じファイルサイズのファイルグループのリスト
    """
    directory = Path(directory)

    if not directory.is_dir():
        raise ValueError(f"指定されたパスはディレクトリではありません: {directory}")

    # ファイルサイズごとにファイルをグループ化
    size_dict: Dict[int, List[FileInfo]] = defaultdict(list)

    # ディレクトリ内の全ファイルを走査
    for root, _, files in os.walk(directory):
        for filename in files:
            filepath = Path(root) / filename
            try:
                # ファイルサイズと属性を取得
                if filepath.is_file():
                    file_size = filepath.stat().st_size
                    file_attrs = get_file_attributes(filepath)
                    file_info = FileInfo(
                        path=str(filepath),
                        size=file_size,
                        attributes=file_attrs
                    )
                    size_dict[file_size].append(file_info)
            except (OSError, PermissionError):
                # アクセスできないファイルはスキップ
                continue

    # 指定された最小グループサイズ以上のグループのみを抽出
    result_groups = []
    for size, files in size_dict.items():
        if len(files) >= min_group_size:
            sorted_files = sorted(files, key=lambda f: f.path)
            result_groups.append(SameFileSizeGroup(size=size, files=sorted_files))

    # ファイル数の多い順、同じ場合はサイズの大きい順にソート
    result_groups.sort(key=lambda g: (-len(g.files), -g.size))

    return result_groups


def format_file_size(size: int) -> str:
    """ファイルサイズを人間が読みやすい形式にフォーマットする"""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size_float = float(size)

    while size_float >= 1024 and unit_index < len(units) - 1:
        size_float /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{size} {units[unit_index]}"
    else:
        return f"{size_float:.2f} {units[unit_index]}"
