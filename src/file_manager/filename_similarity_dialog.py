#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名類似候補を一覧表示するダイアログ。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

try:
    import send2trash

    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

from .filename_similarity import SimilarFileGroup, find_similar_filenames
from .utils import silent_question, silent_information, silent_critical

WORKER_CLEANUP_TIMEOUT_MS = 3000


class FilenameSimilarityWorker(QObject):
    """バックグラウンドで類似ファイル名を検出するワーカー。"""

    progress_changed = Signal(int)
    finished = Signal(list)
    error_occurred = Signal(str)

    def __init__(
        self,
        folder_path: str,
        recursive: bool = False,
        similarity_threshold: float = 0.7,
        min_group_size: int = 2,
        use_file_size: bool = True,
        size_weight: float = 0.3,
    ) -> None:
        super().__init__()
        self.folder_path = folder_path
        self.recursive = recursive
        self.similarity_threshold = similarity_threshold
        self.min_group_size = min_group_size
        self.use_file_size = use_file_size
        self.size_weight = size_weight
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def progress(value: int) -> None:
            self.progress_changed.emit(value)

        def should_stop() -> bool:
            return self._cancelled

        try:
            results = find_similar_filenames(
                self.folder_path,
                recursive=self.recursive,
                extensions=None,
                similarity_threshold=self.similarity_threshold,
                min_group_size=self.min_group_size,
                use_file_size=self.use_file_size,
                size_weight=self.size_weight,
                progress_callback=progress,
                stop_callback=should_stop,
            )
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled:
                self.error_occurred.emit(str(exc))
            return

        if self._cancelled:
            return
        self.finished.emit(results)


class FilenameSimilarityDialog(QDialog):
    """類似ファイル名の検出結果を表示するダイアログ。"""

    def __init__(self, folder_path: str, parent=None) -> None:
        real_parent = parent if (parent is not None and hasattr(parent, "window")) else None
        super().__init__(real_parent)
        self.folder_path = folder_path
        self.worker_thread: QThread | None = None
        self.worker: FilenameSimilarityWorker | None = None
        self.checked_files: set[str] = set()

        self.setWindowTitle(f"ファイル名類似検出 - {Path(folder_path).name or folder_path}")
        self.resize(1100, 720)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.info_label = QLabel(f"対象フォルダ: {self.folder_path}")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.info_label)

        settings_group = QGroupBox("検索設定")
        settings_layout = QFormLayout()

        self.recursive_checkbox = QCheckBox("サブフォルダも含める")
        self.recursive_checkbox.setChecked(False)
        settings_layout.addRow("", self.recursive_checkbox)

        self.similarity_spinbox = QDoubleSpinBox()
        self.similarity_spinbox.setRange(0.1, 1.0)
        self.similarity_spinbox.setSingleStep(0.05)
        self.similarity_spinbox.setValue(0.7)
        self.similarity_spinbox.setDecimals(2)
        self.similarity_spinbox.setSuffix(" (0.0-1.0)")
        settings_layout.addRow("類似度しきい値:", self.similarity_spinbox)

        self.min_group_spinbox = QSpinBox()
        self.min_group_spinbox.setRange(2, 100)
        self.min_group_spinbox.setValue(2)
        self.min_group_spinbox.setSuffix(" ファイル以上")
        settings_layout.addRow("最小グループサイズ:", self.min_group_spinbox)

        self.use_size_checkbox = QCheckBox("ファイルサイズも考慮する")
        self.use_size_checkbox.setChecked(True)
        settings_layout.addRow("", self.use_size_checkbox)

        self.size_weight_spinbox = QDoubleSpinBox()
        self.size_weight_spinbox.setRange(0.0, 0.9)
        self.size_weight_spinbox.setSingleStep(0.1)
        self.size_weight_spinbox.setValue(0.3)
        self.size_weight_spinbox.setDecimals(1)
        self.size_weight_spinbox.setSuffix(" (0.0-0.9)")
        settings_layout.addRow("サイズの重み:", self.size_weight_spinbox)

        self.search_button = QPushButton("検索開始")
        self.search_button.clicked.connect(self._start_search)
        settings_layout.addRow("", self.search_button)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        self.status_label = QLabel("検索条件を確認して、「検索開始」を押してください")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["選択", "ファイル", "類似度", "相対パス", "サイズ"])
        self.tree.setColumnWidth(0, 40)
        self.tree.setColumnWidth(1, 360)
        self.tree.setColumnWidth(2, 90)
        self.tree.setColumnWidth(3, 420)
        self.tree.setColumnWidth(4, 120)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self._on_item_selection_changed)
        layout.addWidget(self.tree, stretch=1)

        self.selection_label = QLabel("選択中: 0 ファイル")
        layout.addWidget(self.selection_label)

        help_label = QLabel(
            "使い方:\n"
            "  ・検索後、削除したいファイルをチェックまたは選択してください\n"
            "  ・「すべて選択」で一覧のファイルをまとめて選択できます\n"
            "  ・選択したファイルはゴミ箱へ移動します\n"
        )
        help_label.setStyleSheet(
            "color: #555; font-size: 9pt; background-color: #f0f0f0; padding: 8px; border-radius: 4px;"
        )
        layout.addWidget(help_label)

        button_layout = QHBoxLayout()

        self.select_all_button = QPushButton("すべて選択")
        self.select_all_button.clicked.connect(self._select_all)
        self.select_all_button.setEnabled(False)
        button_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("選択解除")
        self.deselect_all_button.clicked.connect(self._deselect_all)
        self.deselect_all_button.setEnabled(False)
        button_layout.addWidget(self.deselect_all_button)

        button_layout.addStretch(1)

        self.delete_button = QPushButton("選択したファイルを削除")
        self.delete_button.clicked.connect(self._delete_selected_files)
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("QPushButton { background-color: #d9534f; color: white; }")
        button_layout.addWidget(self.delete_button)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _start_search(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "検索中", "既に検索を実行中です。")
            return

        self.search_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.deselect_all_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.tree.clear()
        self.checked_files.clear()
        self.selection_label.setText("選択中: 0 ファイル")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("類似ファイルを検索中...")

        self.worker_thread = QThread(self)
        self.worker = FilenameSimilarityWorker(
            self.folder_path,
            recursive=self.recursive_checkbox.isChecked(),
            similarity_threshold=self.similarity_spinbox.value(),
            min_group_size=self.min_group_spinbox.value(),
            use_file_size=self.use_size_checkbox.isChecked(),
            size_weight=self.size_weight_spinbox.value(),
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.finished.connect(self._cleanup_worker)
        self.worker.error_occurred.connect(self._cleanup_worker)

        self.worker_thread.start()

    def _cleanup_worker(self) -> None:
        if self.worker:
            self.worker.cancel()
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait(WORKER_CLEANUP_TIMEOUT_MS)
            self.worker_thread.deleteLater()
            self.worker_thread = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        self.search_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _on_worker_finished(self, results: list[SimilarFileGroup]) -> None:
        total_files = sum(len(group.files) for group in results)
        if results:
            self.status_label.setText(f"検索完了: {len(results)} グループ、対象 {total_files} ファイル")
        else:
            self.status_label.setText("見つかりませんでした")

        self.progress_bar.setValue(100)
        self._populate_tree(results)
        self._update_action_state()

    def _on_worker_error(self, message: str) -> None:
        QMessageBox.warning(self, "エラー", f"検索中にエラーが発生しました:\n{message}")
        self.status_label.setText("エラーが発生しました")

    def _populate_tree(self, groups: list[SimilarFileGroup]) -> None:
        self.tree.clear()
        self.checked_files.clear()

        for index, group in enumerate(groups, start=1):
            top_item = QTreeWidgetItem(
                [
                    f"グループ {index} ({len(group.files)} ファイル)",
                    "",
                    f"{group.similarity_score:.2%}",
                    "",
                    f"平均 {self._format_size(group.get_average_size())}",
                ]
            )
            top_item.setFlags(top_item.flags() & ~Qt.ItemIsSelectable)

            font = top_item.font(0)
            font.setBold(True)
            for column in range(5):
                top_item.setFont(column, font)
                top_item.setBackground(column, Qt.lightGray)

            self.tree.addTopLevelItem(top_item)

            for file_path in group.files:
                child = QTreeWidgetItem(
                    [
                        "",
                        Path(file_path).name,
                        "",
                        self._to_relative_path(file_path),
                        self._format_size(group.file_sizes.get(file_path, 0)),
                    ]
                )
                child.setData(0, Qt.UserRole, file_path)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                child.setCheckState(0, Qt.Unchecked)
                top_item.addChild(child)

            top_item.setExpanded(True)

        if groups:
            for column in range(5):
                self.tree.resizeColumnToContents(column)

        self._update_action_state()

    def _to_relative_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self.folder_path))
        except ValueError:
            return file_path

    def _format_size(self, size_bytes: int) -> str:
        size_value = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_value < 1024.0:
                return f"{size_value:.1f} {unit}"
            size_value /= 1024.0
        return f"{size_value:.1f} PB"

    def _selected_file_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        seen_paths: set[str] = set()

        for item in self.tree.selectedItems():
            file_path = item.data(0, Qt.UserRole)
            if file_path and file_path not in seen_paths:
                items.append(item)
                seen_paths.add(file_path)

        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                file_path = child.data(0, Qt.UserRole)
                if file_path and child.checkState(0) == Qt.Checked and file_path not in seen_paths:
                    items.append(child)
                    seen_paths.add(file_path)

        return items

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return

        file_path = item.data(0, Qt.UserRole)
        if not file_path:
            return

        if item.checkState(0) == Qt.Checked:
            self.checked_files.add(file_path)
        else:
            self.checked_files.discard(file_path)

        self._update_action_state()

    def _on_item_selection_changed(self) -> None:
        self._update_action_state()

    def _update_action_state(self) -> None:
        selected_count = len(self._selected_file_items())
        has_results = self.tree.topLevelItemCount() > 0

        self.selection_label.setText(f"選択中: {selected_count} ファイル")
        self.select_all_button.setEnabled(has_results)
        self.deselect_all_button.setEnabled(selected_count > 0)
        self.delete_button.setEnabled(selected_count > 0)

    def _select_all(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clearSelection()
            self.checked_files.clear()
            for i in range(self.tree.topLevelItemCount()):
                group_item = self.tree.topLevelItem(i)
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    child.setSelected(True)
                    child.setCheckState(0, Qt.Checked)
                    file_path = child.data(0, Qt.UserRole)
                    if file_path:
                        self.checked_files.add(file_path)
        finally:
            self.tree.blockSignals(False)

        self._update_action_state()

    def _deselect_all(self) -> None:
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                group_item = self.tree.topLevelItem(i)
                for j in range(group_item.childCount()):
                    group_item.child(j).setCheckState(0, Qt.Unchecked)
        finally:
            self.tree.blockSignals(False)

        self.checked_files.clear()
        self.tree.clearSelection()
        self._update_action_state()

    def _delete_selected_files(self) -> None:
        selected_items = self._selected_file_items()
        if not selected_items:
            silent_information(self, "情報", "削除するファイルが選択されていません。")
            return

        if not HAS_SEND2TRASH:
            silent_critical(
                self,
                "エラー",
                "send2trash がインストールされていません。\n"
                "削除機能を使うには `pip install send2trash` を実行してください。",
            )
            return

        selected_paths = [item.data(0, Qt.UserRole) for item in selected_items]
        reply = silent_question(
            self,
            "確認",
            f"{len(selected_paths)} 個のファイルを削除します。\n"
            "ファイルはゴミ箱へ移動されます。\n\n"
            "本当に削除しますか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_paths: set[str] = set()
        failed_files: list[str] = []

        for file_path in selected_paths:
            try:
                path_obj = Path(file_path)
                if not path_obj.exists():
                    failed_files.append(f"{file_path}: ファイルが見つかりません")
                    continue

                send2trash.send2trash(str(path_obj))
                deleted_paths.add(file_path)
            except Exception as exc:  # noqa: BLE001
                failed_files.append(f"{file_path}: {exc}")

        if deleted_paths:
            self.checked_files.difference_update(deleted_paths)
            self._remove_deleted_items(deleted_paths)
            self.tree.clearSelection()
            self._update_action_state()
            if self.tree.topLevelItemCount() == 0:
                self.status_label.setText("表示できる類似ファイルはありません")

        message = f"{len(deleted_paths)} 個のファイルを削除しました。"
        if failed_files:
            message += f"\n\n{len(failed_files)} 個のファイルの削除に失敗しました:\n"
            message += "\n".join(failed_files[:5])
            if len(failed_files) > 5:
                message += f"\n... 残り{len(failed_files) - 5} 件"

        silent_information(self, "削除完了", message)

    def _remove_deleted_items(self, deleted_paths: set[str]) -> None:
        groups_to_remove: list[int] = []

        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            child_indexes_to_remove: list[int] = []

            for j in range(group_item.childCount()):
                child = group_item.child(j)
                file_path = child.data(0, Qt.UserRole)
                if file_path in deleted_paths:
                    child_indexes_to_remove.append(j)

            for j in reversed(child_indexes_to_remove):
                group_item.takeChild(j)

            if group_item.childCount() == 0:
                groups_to_remove.append(i)

        for i in reversed(groups_to_remove):
            self.tree.takeTopLevelItem(i)

        self._renumber_groups()

    def _renumber_groups(self) -> None:
        for index in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(index)
            group_item.setText(0, f"グループ {index + 1} ({group_item.childCount()} ファイル)")

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        path = item.data(0, Qt.UserRole)
        if path:
            self._open_file(path)

    def _open_file(self, file_path: str) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(file_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", file_path], check=True)
            else:
                subprocess.run(["xdg-open", file_path], check=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{exc}")

    def accept(self) -> None:
        self._cleanup_worker()
        super().accept()

    def reject(self) -> None:
        self._cleanup_worker()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_worker()
        super().closeEvent(event)
