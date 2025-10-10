#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同じファイルサイズのファイルを検出して表示するダイアログ"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Set

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QMessageBox,
    QCheckBox,
    QSpinBox,
    QGroupBox,
    QFormLayout,
    QFileDialog,
)

# send2trashのインポート（オプショナル）
try:
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

from .same_filesize import SameFileSizeGroup, find_same_filesize_files, format_file_size

# 定数
WORKER_CLEANUP_TIMEOUT_MS = 3000  # ワーカークリーンアップのタイムアウト（ミリ秒）


class SameFileSizeWorker(QObject):
    """バックグラウンドで同じファイルサイズ検出を実行するワーカー"""

    progress_changed = Signal(int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, directory: str, min_group_size: int):
        super().__init__()
        self.directory = directory
        self.min_group_size = min_group_size
        self._is_cancelled = False

    def run(self):
        """ワーカーの実行"""
        try:
            # 同じファイルサイズのファイルを検出
            groups = find_same_filesize_files(
                self.directory,
                min_group_size=self.min_group_size
            )

            if not self._is_cancelled:
                self.finished.emit(groups)

        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

    def cancel(self):
        """処理をキャンセル"""
        self._is_cancelled = True


class SameFileSizeDialog(QDialog):
    """同じファイルサイズのファイルを検出して表示するダイアログ"""

    def __init__(self, parent=None, directory: str = ""):
        super().__init__(parent)
        self.directory = directory
        self.groups: List[SameFileSizeGroup] = []
        self.worker: SameFileSizeWorker | None = None
        self.worker_thread: QThread | None = None

        self.setWindowTitle("同じファイルサイズのファイル検出")
        self.resize(900, 600)

        self.setup_ui()

    def setup_ui(self):
        """UIのセットアップ"""
        layout = QVBoxLayout(self)

        # 検索設定グループ
        settings_group = QGroupBox("検索設定")
        settings_layout = QFormLayout()

        # ディレクトリ選択
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel(self.directory or "未選択")
        self.dir_label.setWordWrap(True)
        dir_layout.addWidget(self.dir_label, 1)

        self.dir_button = QPushButton("変更...")
        self.dir_button.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.dir_button)

        settings_layout.addRow("検索ディレクトリ:", dir_layout)

        # 最小グループサイズ
        self.min_group_spinbox = QSpinBox()
        self.min_group_spinbox.setMinimum(2)
        self.min_group_spinbox.setMaximum(100)
        self.min_group_spinbox.setValue(2)
        self.min_group_spinbox.setToolTip("同じサイズのファイルが何個以上あればグループと見なすか")
        settings_layout.addRow("最小グループサイズ:", self.min_group_spinbox)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # 実行ボタン
        button_layout = QHBoxLayout()
        self.scan_button = QPushButton("検出開始")
        self.scan_button.clicked.connect(self.start_scan)
        button_layout.addWidget(self.scan_button)

        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ステータスラベル
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # 結果ツリー
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["ファイル名", "サイズ", "属性", "パス"])
        self.tree_widget.setColumnWidth(0, 250)
        self.tree_widget.setColumnWidth(1, 120)
        self.tree_widget.setColumnWidth(2, 80)
        self.tree_widget.setColumnWidth(3, 400)
        self.tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.tree_widget)

        # アクションボタン
        action_layout = QHBoxLayout()

        self.select_all_button = QPushButton("すべて選択")
        self.select_all_button.clicked.connect(self.select_all_items)
        action_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("すべて選択解除")
        self.deselect_all_button.clicked.connect(self.deselect_all_items)
        action_layout.addWidget(self.deselect_all_button)

        self.open_button = QPushButton("選択したファイルを開く")
        self.open_button.clicked.connect(self.open_selected_files)
        action_layout.addWidget(self.open_button)

        self.reveal_button = QPushButton("エクスプローラーで表示")
        self.reveal_button.clicked.connect(self.reveal_in_explorer)
        action_layout.addWidget(self.reveal_button)

        if HAS_SEND2TRASH:
            self.delete_button = QPushButton("選択したファイルを削除")
            self.delete_button.clicked.connect(self.delete_selected_files)
            action_layout.addWidget(self.delete_button)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # 閉じるボタン
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def select_directory(self):
        """ディレクトリを選択"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "検索ディレクトリを選択",
            self.directory or ""
        )
        if directory:
            self.directory = directory
            self.dir_label.setText(directory)

    def start_scan(self):
        """スキャンを開始"""
        if not self.directory:
            QMessageBox.warning(self, "エラー", "検索ディレクトリを選択してください。")
            return

        # UI状態を更新
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定プログレス
        self.status_label.setText("スキャン中...")
        self.tree_widget.clear()

        # ワーカーとスレッドを作成
        self.worker_thread = QThread()
        self.worker = SameFileSizeWorker(
            self.directory,
            self.min_group_spinbox.value()
        )
        self.worker.moveToThread(self.worker_thread)

        # シグナルを接続
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)

        # スレッドを開始
        self.worker_thread.start()

    def cancel_scan(self):
        """スキャンをキャンセル"""
        if self.worker:
            self.worker.cancel()
        self.cleanup_worker()
        self.status_label.setText("キャンセルされました")
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def on_scan_finished(self, groups: List[SameFileSizeGroup]):
        """スキャン完了時の処理"""
        self.groups = groups
        self.populate_tree()
        self.cleanup_worker()

        # UI状態を更新
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        total_files = sum(len(group.files) for group in groups)
        self.status_label.setText(
            f"完了: {len(groups)} グループ、{total_files} ファイル"
        )

    def on_scan_error(self, error_message: str):
        """スキャンエラー時の処理"""
        self.cleanup_worker()
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("エラーが発生しました")
        QMessageBox.critical(self, "エラー", f"スキャン中にエラーが発生しました:\n{error_message}")

    def cleanup_worker(self):
        """ワーカーとスレッドをクリーンアップ"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            if not self.worker_thread.wait(WORKER_CLEANUP_TIMEOUT_MS):
                self.worker_thread.terminate()
                self.worker_thread.wait()

        self.worker = None
        self.worker_thread = None

    def populate_tree(self):
        """ツリーウィジェットに結果を表示"""
        self.tree_widget.clear()

        for group in self.groups:
            # グループのルートアイテム
            group_item = QTreeWidgetItem(self.tree_widget)
            group_item.setText(0, f"{len(group.files)} 個のファイル")
            group_item.setText(1, format_file_size(group.size))
            group_item.setText(2, "")
            group_item.setText(3, f"ファイルサイズ: {group.size} bytes")
            group_item.setExpanded(True)

            # 各ファイルのアイテム
            for file_info in group.files:
                file_item = QTreeWidgetItem(group_item)
                file_item.setText(0, os.path.basename(file_info.path))
                file_item.setText(1, format_file_size(group.size))
                file_item.setText(2, file_info.attributes)
                file_item.setText(3, file_info.path)
                file_item.setData(0, Qt.UserRole, file_info.path)

    def get_selected_file_paths(self) -> Set[str]:
        """選択されたファイルパスを取得"""
        selected_paths = set()
        for item in self.tree_widget.selectedItems():
            filepath = item.data(0, Qt.UserRole)
            if filepath:  # グループアイテムではなくファイルアイテムのみ
                selected_paths.add(filepath)
        return selected_paths

    def select_all_items(self):
        """すべてのファイルアイテムを選択"""
        iterator = QTreeWidgetItemIterator(self.tree_widget)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.UserRole):  # ファイルアイテムのみ
                item.setSelected(True)
            iterator += 1

    def deselect_all_items(self):
        """すべての選択を解除"""
        self.tree_widget.clearSelection()

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """アイテムがダブルクリックされたときの処理"""
        filepath = item.data(0, Qt.UserRole)
        if filepath:
            self.open_file(filepath)

    def open_selected_files(self):
        """選択されたファイルを開く"""
        selected_paths = self.get_selected_file_paths()
        if not selected_paths:
            QMessageBox.warning(self, "警告", "ファイルが選択されていません。")
            return

        for filepath in selected_paths:
            self.open_file(filepath)

    def open_file(self, filepath: str):
        """ファイルをデフォルトアプリケーションで開く"""
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
            elif sys.platform == "darwin":
                subprocess.run(["open", filepath], check=True)
            else:
                subprocess.run(["xdg-open", filepath], check=True)
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{e}")

    def reveal_in_explorer(self):
        """選択されたファイルをエクスプローラーで表示"""
        selected_paths = self.get_selected_file_paths()
        if not selected_paths:
            QMessageBox.warning(self, "警告", "ファイルが選択されていません。")
            return

        for filepath in selected_paths:
            try:
                if sys.platform == "win32":
                    subprocess.run(["explorer", "/select,", filepath], check=True)
                elif sys.platform == "darwin":
                    subprocess.run(["open", "-R", filepath], check=True)
                else:
                    # Linuxの場合、親ディレクトリを開く
                    parent_dir = os.path.dirname(filepath)
                    subprocess.run(["xdg-open", parent_dir], check=True)
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"エクスプローラーで表示できませんでした:\n{e}")

    def delete_selected_files(self):
        """選択されたファイルを削除（ゴミ箱へ移動）"""
        if not HAS_SEND2TRASH:
            QMessageBox.warning(self, "エラー", "send2trashモジュールがインストールされていません。")
            return

        selected_paths = self.get_selected_file_paths()
        if not selected_paths:
            QMessageBox.warning(self, "警告", "ファイルが選択されていません。")
            return

        reply = QMessageBox.question(
            self,
            "確認",
            f"{len(selected_paths)} 個のファイルをゴミ箱に移動しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            success_count = 0
            error_files = []

            for filepath in selected_paths:
                try:
                    send2trash.send2trash(filepath)
                    success_count += 1
                except Exception as e:
                    error_files.append(f"{filepath}: {e}")

            # 結果を表示
            if error_files:
                QMessageBox.warning(
                    self,
                    "削除エラー",
                    f"{success_count} 個のファイルを削除しました。\n\n"
                    f"以下のファイルで削除エラーが発生しました:\n" +
                    "\n".join(error_files[:10]) +
                    (f"\n... 他 {len(error_files) - 10} 件" if len(error_files) > 10 else "")
                )
            else:
                QMessageBox.information(
                    self,
                    "削除完了",
                    f"{success_count} 個のファイルをゴミ箱に移動しました。"
                )

            # ツリーを更新
            self.remove_deleted_items(selected_paths)

    def remove_deleted_items(self, deleted_paths: Set[str]):
        """削除されたファイルをツリーから削除"""
        iterator = QTreeWidgetItemIterator(self.tree_widget)
        items_to_remove = []

        while iterator.value():
            item = iterator.value()
            filepath = item.data(0, Qt.UserRole)
            if filepath and filepath in deleted_paths:
                items_to_remove.append(item)
            iterator += 1

        # アイテムを削除
        for item in items_to_remove:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
                # 親グループが空になったら削除
                if parent.childCount() == 0:
                    index = self.tree_widget.indexOfTopLevelItem(parent)
                    if index != -1:
                        self.tree_widget.takeTopLevelItem(index)

    def closeEvent(self, event: QCloseEvent):
        """ダイアログを閉じる際の処理"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "確認",
                "スキャンが実行中です。キャンセルして閉じますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if self.worker:
                    self.worker.cancel()
                self.cleanup_worker()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
