"""動画クラスタリング — スキャン進捗ダイアログ + クラスタ/タグ管理ダイアログ。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from .video_cluster_db import VideoClusterDB
from .video_cluster_worker import VideoClusterWorker


# ---------------------------------------------------------------------------
# スキャン進捗ダイアログ
# ---------------------------------------------------------------------------
class VideoClusterScanDialog(QDialog):
    """動画フォルダをスキャンしてクラスタリングを実行するダイアログ。"""

    def __init__(self, db: VideoClusterDB, initial_folder: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("動画クラスタリング — フォルダスキャン")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._db = db
        self._worker: Optional[VideoClusterWorker] = None
        self._build_ui(initial_folder)

    def _build_ui(self, folder: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # フォルダ選択
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit(folder)
        self._folder_edit.setPlaceholderText("スキャンするフォルダのパス")
        browse_btn = QPushButton("参照...")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        folder_row.addWidget(QLabel("フォルダ:"))
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # 説明
        info = QLabel(
            "指定フォルダ以下の動画ファイルを分析し、内容に基づいてタグとクラスタを自動生成します。\n"
            "初回は数分〜数十分かかる場合があります。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #B0B0B0; font-size: 12px;")
        layout.addWidget(info)

        # 進捗
        self._status_label = QLabel("スキャン準備中...")
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)

        # ボタン
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("スキャン開始")
        self._start_btn.setDefault(True)
        self._start_btn.clicked.connect(self._start)
        self._cancel_btn = QPushButton("キャンセル")
        self._cancel_btn.clicked.connect(self._cancel)
        self._close_btn = QPushButton("閉じる")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "フォルダを選択", self._folder_edit.text() or os.path.expanduser("~")
        )
        if folder:
            self._folder_edit.setText(folder)

    def _start(self) -> None:
        folder = self._folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "エラー", "有効なフォルダを指定してください。")
            return
        self._start_btn.setEnabled(False)
        self._folder_edit.setEnabled(False)
        self._close_btn.setEnabled(False)
        self._progress.setValue(0)
        self._status_label.setText("スキャン中...")

        self._worker = VideoClusterWorker(folder, self._db)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._status_label.setText("キャンセル中...")
            self._cancel_btn.setEnabled(False)
        else:
            self.reject()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        if total > 0:
            pct = int(current * 100 / total)
            self._progress.setValue(pct)
        self._status_label.setText(f"処理中 ({current}/{total}): {msg}")

    def _on_finished(self, processed: int, skipped: int) -> None:
        self._progress.setValue(100)
        self._status_label.setText(
            f"完了: {processed} 本を処理、{skipped} 本をスキップ（キャッシュ済み）"
        )
        self._start_btn.setEnabled(True)
        self._folder_edit.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._close_btn.setEnabled(True)

    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"エラー: {msg}")
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._close_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# クラスタ / タグ ブラウザダイアログ
# ---------------------------------------------------------------------------
class VideoClusterBrowserDialog(QDialog):
    """クラスタ一覧・タグ一覧・動画一覧を表示するブラウザ。"""

    def __init__(self, db: VideoClusterDB, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動画クラスタリング — ブラウザ")
        self.setMinimumSize(720, 520)
        self._db = db
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 統計ヘッダ
        self._stats_label = QLabel()
        self._stats_label.setStyleSheet("font-size: 12px; color: #B0B0B0;")
        layout.addWidget(self._stats_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_cluster_tab(), "クラスタ")
        tabs.addTab(self._build_tag_tab(), "タグ")
        layout.addWidget(tabs, 1)

        # 閉じるボタン
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        layout.addWidget(bb)

    def _build_cluster_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)

        # クラスタツリー（左）
        self._cluster_tree = QTreeWidget()
        self._cluster_tree.setHeaderLabels(["クラスタ名", "動画数"])
        self._cluster_tree.setColumnWidth(0, 220)
        self._cluster_tree.itemSelectionChanged.connect(self._on_cluster_selected)

        # 動画リスト（右）
        right = QVBoxLayout()
        self._cluster_video_list = QListWidget()
        self._cluster_video_list.setWordWrap(True)
        right.addWidget(QLabel("所属動画:"))
        right.addWidget(self._cluster_video_list, 1)
        right_w = QWidget()
        right_w.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._cluster_tree)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
        return w

    def _build_tag_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)

        # タグリスト（左）
        self._tag_list = QListWidget()
        self._tag_list.itemSelectionChanged.connect(self._on_tag_selected)

        # 動画リスト（右）
        right = QVBoxLayout()
        self._tag_video_list = QListWidget()
        self._tag_video_list.setWordWrap(True)
        right.addWidget(QLabel("該当動画:"))
        right.addWidget(self._tag_video_list, 1)
        right_w = QWidget()
        right_w.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._tag_list)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        return w

    def _refresh(self) -> None:
        stats = self._db.stats()
        self._stats_label.setText(
            f"動画: {stats['videos']}  タグ: {stats['tags']}  クラスタ: {stats['clusters']}"
        )
        self._load_clusters()
        self._load_tags()

    def _load_clusters(self) -> None:
        self._cluster_tree.clear()
        clusters = self._db.list_clusters()
        for c in clusters:
            item = QTreeWidgetItem([
                c["user_name"] or c["auto_name"] or f"クラスタ {c['id']}",
                str(c["member_count"]),
            ])
            item.setData(0, Qt.UserRole, c["id"])
            color = QColor(c["color"] or "#6200EE")
            item.setForeground(0, color)
            font = QFont()
            font.setBold(True)
            item.setFont(0, font)
            self._cluster_tree.addTopLevelItem(item)

    def _load_tags(self) -> None:
        self._tag_list.clear()
        tags = self._db.get_all_tags_with_counts()
        for t in tags:
            item = QListWidgetItem(f"{t['canonical_tag']}  ({t['cnt']})")
            item.setData(Qt.UserRole, t["canonical_tag"])
            self._tag_list.addItem(item)

    def _on_cluster_selected(self) -> None:
        items = self._cluster_tree.selectedItems()
        self._cluster_video_list.clear()
        if not items:
            return
        cid = items[0].data(0, Qt.UserRole)
        paths = self._db.get_cluster_videos(cid)
        for p in paths:
            self._cluster_video_list.addItem(Path(p).name)
            # ツールチップでフルパス
            self._cluster_video_list.item(self._cluster_video_list.count() - 1).setToolTip(p)

    def _on_tag_selected(self) -> None:
        items = self._tag_list.selectedItems()
        self._tag_video_list.clear()
        if not items:
            return
        tag = items[0].data(Qt.UserRole)
        paths = self._db.get_videos_with_tags([tag])
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            self._tag_video_list.addItem(item)
