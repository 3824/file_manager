#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名類似度ダイアログのテスト"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from src.file_manager.filename_similarity import SimilarFileGroup
from src.file_manager.filename_similarity_dialog import (
    FilenameSimilarityDialog,
    FilenameSimilarityWorker,
)


class TestFilenameSimilarityWorker:
    """FilenameSimilarityWorker のテスト"""

    def test_worker_initialization(self):
        worker = FilenameSimilarityWorker(
            "/test/path", recursive=True, similarity_threshold=0.8, min_group_size=3
        )
        assert worker.folder_path == "/test/path"
        assert worker.recursive is True
        assert worker.similarity_threshold == 0.8
        assert worker.min_group_size == 3
        assert worker._cancelled is False

    def test_worker_cancel(self):
        worker = FilenameSimilarityWorker("/test/path")
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True


@pytest.fixture
def test_folder_with_similar_files():
    """類似ファイルを含むテストフォルダを作成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 類似する動画ファイルを作成
        files = ["video_01.mp4", "video_02.mp4", "video_03.mp4", "other.avi"]
        for filename in files:
            (Path(tmpdir) / filename).touch()
        yield tmpdir


class TestFilenameSimilarityDialog:
    """FilenameSimilarityDialog のテスト"""

    def test_dialog_initialization(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        assert dialog.folder_path == test_folder_with_similar_files
        assert dialog.windowTitle().startswith("ファイル名類似検出")

    def test_ui_components_exist(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # 主要なUIコンポーネントの存在確認
        assert dialog.info_label is not None
        assert dialog.tree is not None
        assert dialog.search_button is not None
        assert dialog.close_button is not None
        assert dialog.export_button is not None
        assert dialog.recursive_checkbox is not None
        assert dialog.similarity_spinbox is not None
        assert dialog.min_group_spinbox is not None
        assert dialog.use_size_checkbox is not None
        assert dialog.size_weight_spinbox is not None
        assert dialog.delete_button is not None
        assert dialog.select_all_button is not None
        assert dialog.deselect_all_button is not None

    def test_initial_ui_state(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # 初期状態の確認
        assert dialog.search_button.isEnabled()
        assert dialog.close_button.isEnabled()
        assert not dialog.export_button.isEnabled()
        assert not dialog.delete_button.isEnabled()
        assert not dialog.select_all_button.isEnabled()
        assert not dialog.deselect_all_button.isEnabled()
        assert not dialog.progress_bar.isVisible()
        assert dialog.recursive_checkbox.isChecked() is False
        assert dialog.similarity_spinbox.value() == 0.7
        assert dialog.min_group_spinbox.value() == 2
        assert dialog.use_size_checkbox.isChecked() is True
        assert dialog.size_weight_spinbox.value() == 0.3

    def test_populate_tree_with_results(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # テスト用のダミー結果
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

        # ツリーに結果が表示されているか確認
        assert dialog.tree.topLevelItemCount() == 1
        top_item = dialog.tree.topLevelItem(0)
        assert top_item.childCount() == 2
        # 新しいカラム構造: ["☑", "ファイル名", "サイズ", "類似度", "相対パス"]
        assert "グループ 1" in top_item.text(1)  # カラム1にグループ名
        assert "95.00%" in top_item.text(3)  # カラム3に類似度

    def test_relative_path_conversion(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # 相対パス変換のテスト
        full_path = str(Path(test_folder_with_similar_files) / "subdir" / "file.mp4")
        relative = dialog._to_relative_path(full_path)
        assert "subdir" in relative or relative == full_path

    def test_worker_finished_updates_ui(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        test_groups = [
            SimilarFileGroup(
                representative_name="test.mp4",
                files=["/path/test1.mp4", "/path/test2.mp4"],
                similarity_score=0.9,
            )
        ]

        # finished シグナルをシミュレート
        dialog._on_worker_finished(test_groups)

        # UIが更新されているか確認
        assert dialog.export_button.isEnabled()
        assert "検索完了" in dialog.status_label.text()
        assert dialog.tree.topLevelItemCount() > 0

    def test_worker_finished_no_results(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # 空の結果で finished をシミュレート
        dialog._on_worker_finished([])

        # UIが適切に更新されているか確認
        assert not dialog.export_button.isEnabled()
        assert "見つかりませんでした" in dialog.status_label.text()
        assert dialog.tree.topLevelItemCount() == 0

    def test_worker_error_handling(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
            dialog._on_worker_error("Test error message")
            mock_warning.assert_called_once()
            assert "エラーが発生しました" in dialog.status_label.text()

    def test_cleanup_worker(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # ワーカーをモック
        mock_worker = MagicMock()
        mock_thread = MagicMock()
        dialog.worker = mock_worker
        dialog.worker_thread = mock_thread

        dialog._cleanup_worker()

        # クリーンアップが呼ばれたか確認
        mock_worker.cancel.assert_called_once()
        mock_thread.quit.assert_called_once()

    def test_search_settings_persistence(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        # 設定を変更
        dialog.recursive_checkbox.setChecked(True)
        dialog.similarity_spinbox.setValue(0.85)
        dialog.min_group_spinbox.setValue(3)
        dialog.use_size_checkbox.setChecked(False)
        dialog.size_weight_spinbox.setValue(0.5)

        # 値が保持されているか確認
        assert dialog.recursive_checkbox.isChecked() is True
        assert dialog.similarity_spinbox.value() == 0.85
        assert dialog.min_group_spinbox.value() == 3
        assert dialog.use_size_checkbox.isChecked() is False
        assert dialog.size_weight_spinbox.value() == 0.5
