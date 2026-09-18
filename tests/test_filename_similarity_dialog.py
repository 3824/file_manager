#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名類似度ダイアログのテスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

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
def test_folder_with_similar_files(tmp_path):
    for filename in ["video_01.mp4", "video_02.mp4", "video_03.mp4", "other.avi"]:
        (tmp_path / filename).write_bytes(b"test content")
    return str(tmp_path)


class TestFilenameSimilarityDialog:
    def test_dialog_initialization(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        assert dialog.folder_path == test_folder_with_similar_files
        assert dialog.windowTitle().startswith("ファイル名類似検出")

    def test_ui_components_exist(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        assert dialog.info_label is not None
        assert dialog.tree is not None
        assert dialog.search_button is not None
        assert dialog.close_button is not None
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

        assert dialog.search_button.isEnabled()
        assert dialog.close_button.isEnabled()
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

        assert dialog.tree.topLevelItemCount() == 1
        top_item = dialog.tree.topLevelItem(0)
        assert top_item.childCount() == 2
        assert "グループ 1" in top_item.text(0)
        assert "95.00%" in top_item.text(2)
        assert top_item.child(0).text(3) == "video_01.mp4"

    def test_relative_path_conversion(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

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

        dialog._on_worker_finished(test_groups)

        assert dialog.select_all_button.isEnabled()
        assert "検索完了" in dialog.status_label.text()
        assert dialog.tree.topLevelItemCount() > 0

    def test_worker_finished_no_results(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        dialog._on_worker_finished([])

        assert not dialog.select_all_button.isEnabled()
        assert "見つかりませんでした" in dialog.status_label.text()
        assert dialog.tree.topLevelItemCount() == 0

    def test_worker_error_handling(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
            dialog._on_worker_error("Test error message")
            mock_warning.assert_called_once()
            assert "エラー" in dialog.status_label.text()

    def test_cleanup_worker(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        mock_worker = MagicMock()
        mock_thread = MagicMock()
        dialog.worker = mock_worker
        dialog.worker_thread = mock_thread

        dialog._cleanup_worker()

        mock_worker.cancel.assert_called_once()
        mock_thread.quit.assert_called_once()

    def test_search_settings_persistence(self, qtbot: QtBot, test_folder_with_similar_files):
        dialog = FilenameSimilarityDialog(test_folder_with_similar_files)
        qtbot.addWidget(dialog)

        dialog.recursive_checkbox.setChecked(True)
        dialog.similarity_spinbox.setValue(0.85)
        dialog.min_group_spinbox.setValue(3)
        dialog.use_size_checkbox.setChecked(False)
        dialog.size_weight_spinbox.setValue(0.5)

        assert dialog.recursive_checkbox.isChecked() is True
        assert dialog.similarity_spinbox.value() == 0.85
        assert dialog.min_group_spinbox.value() == 3
        assert dialog.use_size_checkbox.isChecked() is False
        assert dialog.size_weight_spinbox.value() == 0.5
