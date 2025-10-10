#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ファイル名類似度による同一ファイル検出ダイアログ"""

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
    QDoubleSpinBox,
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

from .filename_similarity import SimilarFileGroup, find_similar_filenames

# 定数
WORKER_CLEANUP_TIMEOUT_MS = 3000  # ワーカークリーンアップのタイムアウト（ミリ秒）


class FilenameSimilarityWorker(QObject):
    """バックグラウンドでファイル名類似度検出を実行するワーカー"""

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
                extensions=None,  # すべてのファイル
                similarity_threshold=self.similarity_threshold,
                min_group_size=self.min_group_size,
                use_file_size=self.use_file_size,
                size_weight=self.size_weight,
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


class FilenameSimilarityDialog(QDialog):
    """ファイル名の類似度から同一と思われるファイルを一覧表示するダイアログ"""

    def __init__(self, folder_path: str, parent=None) -> None:
        real_parent = parent if (parent is not None and hasattr(parent, "window")) else None
        super().__init__(real_parent)
        self.folder_path = folder_path
        self.worker_thread: QThread | None = None
        self.worker: FilenameSimilarityWorker | None = None
        self.checked_files: Set[str] = set()  # チェックされたファイルのパス

        self.setWindowTitle(f"ファイル名類似検出 - {Path(folder_path).name or folder_path}")
        self.resize(1200, 750)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # フォルダ情報
        self.info_label = QLabel(f"対象フォルダ: {self.folder_path}")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.info_label)

        # 検索設定グループ
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

        # ファイルサイズ考慮のチェックボックス
        self.use_size_checkbox = QCheckBox("ファイルサイズも考慮する（推奨）")
        self.use_size_checkbox.setChecked(True)
        settings_layout.addRow("", self.use_size_checkbox)

        # サイズの重み
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

        # ステータス表示
        self.status_label = QLabel("検索設定を調整して「検索開始」をクリックしてください")
        layout.addWidget(self.status_label)

        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 結果ツリー
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "ファイル名", "サイズ", "類似度"])
        self.tree.setColumnWidth(0, 40)  # チェックボックス用に少し広げる
        self.tree.setColumnWidth(1, 500)
        self.tree.setColumnWidth(2, 100)
        self.tree.setColumnWidth(3, 80)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        # 選択情報ラベル
        self.selection_label = QLabel("チェック済み: 0 ファイル")
        layout.addWidget(self.selection_label)

        # 説明ラベル
        help_label = QLabel(
            "■ 使い方:\n"
            "  ・ファイル名の左側のチェックボックスで削除したいファイルを選択\n"
            "  ・「すべて選択」で全ファイルを選択、「すべて解除」で選択を解除\n"
            "  ・「チェック済みファイルを削除」でゴミ箱に移動（復元可能）\n"
            "  ・ファイル名をダブルクリックで開く\n"
            "  ・「ファイルサイズも考慮する」をオンにすると、サイズが近いファイルを優先的にグループ化"
        )
        help_label.setStyleSheet("color: #555; font-size: 9pt; background-color: #f0f0f0; padding: 8px; border-radius: 4px;")
        layout.addWidget(help_label)

        # ボタン
        button_layout = QHBoxLayout()

        self.select_all_button = QPushButton("すべて選択")
        self.select_all_button.clicked.connect(self._select_all)
        self.select_all_button.setEnabled(False)
        button_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("すべて解除")
        self.deselect_all_button.clicked.connect(self._deselect_all)
        self.deselect_all_button.setEnabled(False)
        button_layout.addWidget(self.deselect_all_button)

        button_layout.addStretch(1)

        self.delete_button = QPushButton("チェック済みファイルを削除")
        self.delete_button.clicked.connect(self._delete_checked_files)
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("QPushButton { background-color: #d9534f; color: white; }")
        button_layout.addWidget(self.delete_button)

        self.export_button = QPushButton("結果をエクスポート")
        self.export_button.clicked.connect(self._export_results)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.export_button)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _start_search(self) -> None:
        """検索を開始"""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "検索中", "既に検索が実行中です")
            return

        # UI状態の更新
        self.search_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.deselect_all_button.setEnabled(False)
        self.tree.clear()
        self.checked_files.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("類似ファイルを検索中...")
        self._update_selection_label()

        # ワーカーの起動
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
        """ワーカーのクリーンアップ"""
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

        # UI状態の復元
        self.search_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _on_worker_finished(self, results: List[SimilarFileGroup]) -> None:
        """検索完了時の処理"""
        total_files = sum(len(group.files) for group in results)
        self.status_label.setText(
            f"検索完了: {len(results)} グループ、合計 {total_files} ファイル"
            if results
            else "類似ファイルは見つかりませんでした"
        )
        self.progress_bar.setValue(100)
        self.export_button.setEnabled(bool(results))
        self.select_all_button.setEnabled(bool(results))
        self.deselect_all_button.setEnabled(bool(results))
        self._populate_tree(results)

    def _on_worker_error(self, message: str) -> None:
        """エラー発生時の処理"""
        QMessageBox.warning(self, "エラー", f"検索中にエラーが発生しました:\n{message}")
        self.status_label.setText("エラーが発生しました")

    def _populate_tree(self, groups: List[SimilarFileGroup]) -> None:
        """ツリーウィジェットに結果を表示"""
        self.tree.clear()
        self.tree.setHeaderLabels(["", "ファイル名", "サイズ", "類似度"])

        for index, group in enumerate(groups, start=1):
            # グループの親アイテム
            group_title = f"グループ {index} ({len(group.files)} ファイル)"
            similarity_text = f"{group.similarity_score:.2%}"
            avg_size = group.get_average_size()
            size_text = self._format_size(avg_size)

            top_item = QTreeWidgetItem(["", group_title, f"平均: {size_text}", similarity_text])

            # グループアイテムを太字に
            font = top_item.font(1)
            font.setBold(True)
            for col in range(4):
                top_item.setFont(col, font)

            # 背景色を設定
            for col in range(4):
                top_item.setBackground(col, Qt.lightGray)

            self.tree.addTopLevelItem(top_item)

            # 各ファイルを子アイテムとして追加
            for file_path in group.files:
                file_name = Path(file_path).name
                file_size = group.file_sizes.get(file_path, 0)
                size_text = self._format_size(file_size)

                # チェックボックス用のアイテムを作成
                child = QTreeWidgetItem(["", file_name, size_text, ""])

                # チェックボックスを有効化（カラム0に設定）
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                child.setCheckState(0, Qt.Unchecked)

                # フルパスを保存
                child.setData(0, Qt.UserRole, file_path)

                # 親アイテムに追加
                top_item.addChild(child)

            top_item.setExpanded(True)

        if groups:
            self.tree.resizeColumnToContents(1)
            self.tree.resizeColumnToContents(2)
            self.tree.resizeColumnToContents(3)

    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズを人間が読みやすい形式に変換"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"


    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """チェックボックスの状態が変更されたとき"""
        if column != 0:
            return

        file_path = item.data(0, Qt.UserRole)
        if not file_path:
            return

        if item.checkState(0) == Qt.Checked:
            self.checked_files.add(file_path)
        else:
            self.checked_files.discard(file_path)

        self._update_selection_label()
        self.delete_button.setEnabled(len(self.checked_files) > 0)

    def _update_selection_label(self) -> None:
        """選択情報ラベルを更新"""
        count = len(self.checked_files)
        self.selection_label.setText(f"チェック済み: {count} ファイル")

    def _select_all(self) -> None:
        """すべてのファイルを選択"""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.UserRole):  # ファイルアイテムのみ
                item.setCheckState(0, Qt.Checked)
            iterator += 1

    def _deselect_all(self) -> None:
        """すべてのファイルの選択を解除"""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.UserRole):  # ファイルアイテムのみ
                item.setCheckState(0, Qt.Unchecked)
            iterator += 1

    def _delete_checked_files(self) -> None:
        """チェックされたファイルを削除"""
        if not self.checked_files:
            QMessageBox.information(self, "情報", "削除するファイルが選択されていません。")
            return

        # send2trashが利用できない場合の警告
        if not HAS_SEND2TRASH:
            QMessageBox.critical(
                self,
                "エラー",
                "send2trashライブラリがインストールされていません。\n"
                "ファイルを削除するには、以下のコマンドでインストールしてください:\n\n"
                "pip install send2trash",
            )
            return

        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            f"{len(self.checked_files)} 個のファイルを削除します。\n"
            "ファイルはゴミ箱に移動されます。\n\n"
            "本当に削除しますか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # ファイルを削除
        deleted_count = 0
        failed_files = []

        for file_path in self.checked_files:
            try:
                path_obj = Path(file_path)
                if path_obj.exists():
                    # ゴミ箱に移動
                    send2trash.send2trash(str(path_obj))
                    deleted_count += 1
            except Exception as exc:
                failed_files.append(f"{file_path}: {exc}")

        # 結果を表示
        if deleted_count > 0:
            # ツリーから削除されたアイテムを除去
            self._remove_deleted_items()
            self.checked_files.clear()
            self._update_selection_label()
            self.delete_button.setEnabled(False)

        message = f"{deleted_count} 個のファイルを削除しました。"
        if failed_files:
            message += f"\n\n{len(failed_files)} 個のファイルの削除に失敗しました:\n"
            message += "\n".join(failed_files[:5])  # 最初の5件のみ表示
            if len(failed_files) > 5:
                message += f"\n... 他 {len(failed_files) - 5} 件"

        QMessageBox.information(self, "削除完了", message)

    def _remove_deleted_items(self) -> None:
        """削除されたファイルをツリーから除去"""
        root = self.tree.invisibleRootItem()
        groups_to_remove = []

        for i in range(root.childCount()):
            group_item = root.child(i)
            files_to_remove = []

            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                file_path = file_item.data(0, Qt.UserRole)
                if file_path and file_path in self.checked_files:
                    files_to_remove.append(j)

            # 子アイテムを逆順で削除
            for j in reversed(files_to_remove):
                group_item.takeChild(j)

            # グループに子がなくなった場合、グループも削除対象に
            if group_item.childCount() == 0:
                groups_to_remove.append(i)

        # グループを逆順で削除
        for i in reversed(groups_to_remove):
            root.takeChild(i)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """アイテムダブルクリック時の処理"""
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        self._open_file(path)

    def _open_file(self, file_path: str) -> None:
        """ファイルを既定のアプリケーションで開く"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(file_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", file_path], check=True)
            else:
                subprocess.run(["xdg-open", file_path], check=True)
        except Exception as exc:  # noqa: BLE001 - UIでユーザー通知
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{exc}")

    def _export_results(self) -> None:
        """結果をテキストファイルにエクスポート"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "結果をエクスポート",
            str(Path.home() / "similar_files.txt"),
            "テキストファイル (*.txt);;すべてのファイル (*.*)",
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"ファイル名類似検出結果\n")
                f.write(f"対象フォルダ: {self.folder_path}\n")
                f.write(f"類似度しきい値: {self.similarity_spinbox.value():.2f}\n")
                f.write(f"最小グループサイズ: {self.min_group_spinbox.value()}\n")
                f.write(f"サブフォルダを含む: {'はい' if self.recursive_checkbox.isChecked() else 'いいえ'}\n")
                f.write(f"ファイルサイズ考慮: {'はい' if self.use_size_checkbox.isChecked() else 'いいえ'}\n")
                f.write("=" * 80 + "\n\n")

                for i in range(self.tree.topLevelItemCount()):
                    group_item = self.tree.topLevelItem(i)
                    f.write(f"{group_item.text(1)}\n")
                    f.write(f"  類似度: {group_item.text(3)}\n")
                    f.write(f"  平均サイズ: {group_item.text(2)}\n")
                    f.write(f"  ファイル一覧:\n")

                    for j in range(group_item.childCount()):
                        child = group_item.child(j)
                        file_path_str = child.data(0, Qt.UserRole)
                        file_size = child.text(2)
                        f.write(f"    - {Path(file_path_str).name} ({file_size})\n")
                        f.write(f"      {file_path_str}\n")

                    f.write("\n")

            QMessageBox.information(
                self, "エクスポート完了", f"結果を以下のファイルに保存しました:\n{file_path}"
            )
        except Exception as exc:  # noqa: BLE001 - UIでユーザー通知
            QMessageBox.warning(self, "エラー", f"エクスポートに失敗しました:\n{exc}")

    def accept(self) -> None:
        """ダイアログを閉じる"""
        self._cleanup_worker()
        super().accept()

    def reject(self) -> None:
        """ダイアログをキャンセル"""
        self._cleanup_worker()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウを閉じる"""
        self._cleanup_worker()
        super().closeEvent(event)
