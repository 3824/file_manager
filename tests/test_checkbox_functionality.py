#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チェックボックス機能のテスト"""

import tempfile
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtCore import Qt, QCoreApplication

from src.file_manager.filename_similarity import SimilarFileGroup
from src.file_manager.filename_similarity_dialog import FilenameSimilarityDialog


@pytest.fixture
def test_folder_with_similar_files():
    """類似ファイルを含むテストフォルダを作成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 類似する動画ファイルを作成
        files = ["video_01.mp4", "video_02.mp4", "video_03.mp4"]
        for filename in files:
            (Path(tmpdir) / filename).write_bytes(b"test content")
        yield tmpdir


class TestCheckboxFunctionality:
    """チェックボックス機能のテスト"""

    def test_checkbox_appears_in_tree(self, qtbot: QtBot, test_folder_with_similar_files):
        """ツリーにチェックボックスが表示されるか"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # テスト用のグループを作成
        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"),
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"),
                ],
                similarity_score=0.95,
                file_sizes={
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"): 1000,
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"): 1100,
                },
            )
        ]

        dialog._populate_tree(test_groups)

        # ツリーアイテムを取得
        top_item = dialog.tree.topLevelItem(0)
        assert top_item is not None
        assert top_item.childCount() == 2

        # 子アイテム（ファイル）を確認
        for i in range(top_item.childCount()):
            child = top_item.child(i)
            # チェックボックスが有効か確認
            assert child.flags() & Qt.ItemIsUserCheckable
            # 初期状態はチェックなし
            assert child.checkState(0) == Qt.Unchecked

    def test_checkbox_state_changes(self, qtbot: QtBot, test_folder_with_similar_files):
        """チェックボックスの状態が変更できるか"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[str(Path(test_folder_with_similar_files) / "video_01.mp4")],
                similarity_score=1.0,
                file_sizes={str(Path(test_folder_with_similar_files) / "video_01.mp4"): 1000},
            )
        ]

        dialog._populate_tree(test_groups)

        top_item = dialog.tree.topLevelItem(0)
        child = top_item.child(0)

        # チェック状態を変更
        child.setCheckState(0, Qt.Checked)
        assert child.checkState(0) == Qt.Checked

        # チェックを外す
        child.setCheckState(0, Qt.Unchecked)
        assert child.checkState(0) == Qt.Unchecked

    def test_checked_files_tracking(self, qtbot: QtBot, test_folder_with_similar_files):
        """チェックされたファイルが追跡されるか"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        file_path = str(Path(test_folder_with_similar_files) / "video_01.mp4")
        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[file_path],
                similarity_score=1.0,
                file_sizes={file_path: 1000},
            )
        ]

        dialog._populate_tree(test_groups)

        top_item = dialog.tree.topLevelItem(0)
        child = top_item.child(0)

        # 初期状態: チェックなし
        assert len(dialog.checked_files) == 0
        assert not dialog.delete_button.isEnabled()

        # チェックを入れる
        child.setCheckState(0, Qt.Checked)
        # itemChanged シグナルが発火するまで待機
        QCoreApplication.processEvents()

        # チェックされたファイルが追跡される
        assert file_path in dialog.checked_files
        assert len(dialog.checked_files) == 1

    def test_select_all_functionality(self, qtbot: QtBot, test_folder_with_similar_files):
        """すべて選択機能のテスト"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"),
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"),
                ],
                similarity_score=0.95,
                file_sizes={
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"): 1000,
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"): 1100,
                },
            )
        ]

        dialog._populate_tree(test_groups)
        dialog.select_all_button.setEnabled(True)

        # すべて選択を実行
        dialog._select_all()
        QCoreApplication.processEvents()

        # すべてのファイルがチェックされている
        top_item = dialog.tree.topLevelItem(0)
        for i in range(top_item.childCount()):
            child = top_item.child(i)
            assert child.checkState(0) == Qt.Checked

    def test_deselect_all_functionality(self, qtbot: QtBot, test_folder_with_similar_files):
        """すべて解除機能のテスト"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"),
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"),
                ],
                similarity_score=0.95,
                file_sizes={
                    str(Path(test_folder_with_similar_files) / "video_01.mp4"): 1000,
                    str(Path(test_folder_with_similar_files) / "video_02.mp4"): 1100,
                },
            )
        ]

        dialog._populate_tree(test_groups)
        dialog.select_all_button.setEnabled(True)
        dialog.deselect_all_button.setEnabled(True)

        # まずすべて選択
        dialog._select_all()
        QCoreApplication.processEvents()

        # すべて解除
        dialog._deselect_all()
        QCoreApplication.processEvents()

        # すべてのファイルのチェックが外れている
        top_item = dialog.tree.topLevelItem(0)
        for i in range(top_item.childCount()):
            child = top_item.child(i)
            assert child.checkState(0) == Qt.Unchecked

    def test_delete_button_enables_when_checked(self, qtbot: QtBot, test_folder_with_similar_files):
        """ファイルをチェックすると削除ボタンが有効になるか"""
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        file_path = str(Path(test_folder_with_similar_files) / "video_01.mp4")
        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[file_path],
                similarity_score=1.0,
                file_sizes={file_path: 1000},
            )
        ]

        dialog._populate_tree(test_groups)

        # 初期状態: 削除ボタンは無効
        assert not dialog.delete_button.isEnabled()

        # ファイルをチェック
        top_item = dialog.tree.topLevelItem(0)
        child = top_item.child(0)
        child.setCheckState(0, Qt.Checked)
        QCoreApplication.processEvents()

        # 削除ボタンが有効になる
        assert dialog.delete_button.isEnabled()
