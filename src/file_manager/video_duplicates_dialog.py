#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動画ファイル重複一覧ダイアログ"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
)

from .video_duplicates import DuplicateGroup, find_duplicate_videos


class VideoDuplicatesWorker(QObject):
    """バックグラウンドで重複検出を実行するワーカー"""

    progress_changed = Signal(int)
    finished = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, folder_path: str, recursive: bool = True) -> None:
        super().__init__()
        self.folder_path = folder_path
        self.recursive = recursive
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def progress(value: int) -> None:
            self.progress_changed.emit(value)

        def should_stop() -> bool:
            return self._cancelled

        try:
            results = find_duplicate_videos(
                self.folder_path,
                recursive=self.recursive,
                progress_callback=progress,
                stop_callback=should_stop,
            )
        except Exception as exc:  # noqa: BLE001 - UI側で通知
            if not self._cancelled:
                self.error_occurred.emit(str(exc))
            return

        if self._cancelled:
            return
        self.finished.emit(results)


class VideoDuplicatesDialog(QDialog):
    """同一と思われる動画ファイルを一覧表示するダイアログ"""

    def __init__(self, folder_path: str, parent=None) -> None:
        real_parent = parent if (parent is not None and hasattr(parent, "window")) else None
        super().__init__(real_parent)
        self.folder_path = folder_path
        self.worker_thread: QThread | None = None
        self.worker: VideoDuplicatesWorker | None = None

        self.setWindowTitle(f"重複動画ファイル - {Path(folder_path).name or folder_path}")
        self.resize(900, 600)

        self._init_ui()
        self._start_worker()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.info_label = QLabel(f"対象フォルダ: {self.folder_path}")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.info_label)

        self.status_label = QLabel("重複を解析中です...")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["ファイル / グループ", "サイズ", "SHA-256"])
        self.tree.setColumnWidth(0, 520)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree, stretch=1)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setEnabled(False)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _start_worker(self) -> None:
        self.worker_thread = QThread(self)
        self.worker = VideoDuplicatesWorker(self.folder_path)
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
            self.worker_thread.wait(3000)
            self.worker_thread.deleteLater()
            self.worker_thread = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _on_worker_finished(self, results: List[DuplicateGroup]) -> None:
        self.status_label.setText(
            "重複ファイルが見つかりました" if results else "重複ファイルは見つかりませんでした"
        )
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.close_button.setEnabled(True)
        self._populate_tree(results)

    def _on_worker_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.close_button.setEnabled(True)
        QMessageBox.warning(self, "エラー", f"重複検出中にエラーが発生しました:\n{message}")
        self.status_label.setText("エラーが発生しました")

    def _populate_tree(self, groups: List[DuplicateGroup]) -> None:
        self.tree.clear()
        for index, group in enumerate(groups, start=1):
            group_title = f"グループ {index} ({len(group.files)} 件)"
            size_text = f"{group.size:,} バイト"
            top_item = QTreeWidgetItem([group_title, size_text, group.sha256])
            top_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(top_item)

            for file_path in group.files:
                relative = self._to_relative_path(file_path)
                child = QTreeWidgetItem([relative, "", ""])
                child.setData(0, Qt.UserRole, file_path)
                top_item.addChild(child)

            top_item.setExpanded(True)

        if groups:
            self.tree.resizeColumnToContents(0)

    def _to_relative_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self.folder_path))
        except ValueError:
            return file_path

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        self._open_file(path)

    def _open_file(self, file_path: str) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(file_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{file_path}'")
            else:
                os.system(f"xdg-open '{file_path}'")
        except Exception as exc:  # noqa: BLE001 - UIでユーザー通知
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{exc}")

    def accept(self) -> None:
        self._cleanup_worker()
        super().accept()

    def reject(self) -> None:
        self._cleanup_worker()
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._cleanup_worker()
        super().closeEvent(event)
