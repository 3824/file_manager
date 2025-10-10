#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チェックボックスの詳細なテスト"""

import tempfile
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtCore import Qt

from src.file_manager.filename_similarity import SimilarFileGroup
from src.file_manager.filename_similarity_dialog import FilenameSimilarityDialog


@pytest.fixture
def test_folder():
    """テストフォルダを作成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        files = ["video_01.mp4", "video_02.mp4"]
        for filename in files:
            (Path(tmpdir) / filename).write_bytes(b"test")
        yield tmpdir


def test_checkbox_flags_and_state(qtbot: QtBot, test_folder):
    """チェックボックスのフラグと状態の詳細確認"""
    dialog = FilenameSimilarityDialog(test_folder)
    qtbot.addWidget(dialog)

    # テストグループ
    file1 = str(Path(test_folder) / "video_01.mp4")
    file2 = str(Path(test_folder) / "video_02.mp4")

    test_groups = [
        SimilarFileGroup(
            representative_name="video_01.mp4",
            files=[file1, file2],
            similarity_score=0.95,
            file_sizes={file1: 1000, file2: 1100},
        )
    ]

    dialog._populate_tree(test_groups)

    # グループアイテムを取得
    top_item = dialog.tree.topLevelItem(0)
    assert top_item is not None, "グループアイテムが存在しない"
    assert top_item.childCount() == 2, f"子アイテム数が正しくない: {top_item.childCount()}"

    # 各子アイテム（ファイル）を確認
    for i in range(top_item.childCount()):
        child = top_item.child(i)

        # カラム0のテキスト確認
        col0_text = child.text(0)
        print(f"ファイル{i}: カラム0='{col0_text}', len={len(col0_text)}")

        # フラグ確認
        flags = child.flags()
        is_checkable = bool(flags & Qt.ItemIsUserCheckable)
        is_enabled = bool(flags & Qt.ItemIsEnabled)
        is_selectable = bool(flags & Qt.ItemIsSelectable)

        print(f"  UserCheckable: {is_checkable}")
        print(f"  Enabled: {is_enabled}")
        print(f"  Selectable: {is_selectable}")

        assert is_checkable, f"ファイル{i}がチェック可能でない"
        assert is_enabled, f"ファイル{i}が有効でない"

        # チェック状態確認
        check_state = child.checkState(0)
        print(f"  CheckState: {check_state} (0=Unchecked, 1=PartiallyChecked, 2=Checked)")
        assert check_state == Qt.Unchecked, f"ファイル{i}の初期状態が正しくない"

        # データ確認
        file_path = child.data(0, Qt.UserRole)
        assert file_path is not None, f"ファイル{i}のパスが保存されていない"
        print(f"  FilePath: {file_path}")


def test_checkbox_click_behavior(qtbot: QtBot, test_folder):
    """チェックボックスのクリック動作テスト"""
    dialog = FilenameSimilarityDialog(test_folder)
    qtbot.addWidget(dialog)

    file1 = str(Path(test_folder) / "video_01.mp4")
    test_groups = [
        SimilarFileGroup(
            representative_name="video_01.mp4",
            files=[file1],
            similarity_score=1.0,
            file_sizes={file1: 1000},
        )
    ]

    dialog._populate_tree(test_groups)

    top_item = dialog.tree.topLevelItem(0)
    child = top_item.child(0)

    # 初期状態
    assert child.checkState(0) == Qt.Unchecked
    assert len(dialog.checked_files) == 0

    # チェックを入れる
    print("チェックを入れます...")
    child.setCheckState(0, Qt.Checked)
    print(f"CheckState after: {child.checkState(0)}")

    # Qt のイベント処理
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()

    # 状態確認
    assert child.checkState(0) == Qt.Checked, "チェック状態が変更されていない"
    print(f"checked_files: {dialog.checked_files}")
    assert file1 in dialog.checked_files, "チェックされたファイルが追跡されていない"


def test_visual_checkbox_elements(qtbot: QtBot, test_folder):
    """チェックボックスの視覚要素テスト"""
    dialog = FilenameSimilarityDialog(test_folder)
    qtbot.addWidget(dialog)

    file1 = str(Path(test_folder) / "video_01.mp4")
    test_groups = [
        SimilarFileGroup(
            representative_name="video_01.mp4",
            files=[file1],
            similarity_score=1.0,
            file_sizes={file1: 1000},
        )
    ]

    dialog._populate_tree(test_groups)

    # ツリー設定確認
    assert dialog.tree.columnCount() == 5, "カラム数が正しくない"
    assert dialog.tree.columnWidth(0) >= 30, "カラム0の幅が狭すぎる"

    # ヘッダー確認
    header = dialog.tree.headerItem()
    header_text = header.text(0)
    print(f"カラム0のヘッダー: '{header_text}'")

    # アイテム確認
    top_item = dialog.tree.topLevelItem(0)
    child = top_item.child(0)

    # すべてのカラムのテキストを確認
    for col in range(5):
        text = child.text(col)
        print(f"カラム{col}: '{text}'")

    # カラム0が空白またはスペースであることを確認
    col0 = child.text(0)
    assert len(col0) in [0, 1], f"カラム0のテキストが想定外: '{col0}'"

    # ファイル名がカラム1にあることを確認
    assert "video_01.mp4" in child.text(1), "ファイル名が正しい位置にない"
