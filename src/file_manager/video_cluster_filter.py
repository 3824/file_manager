"""動画クラスタリング — タグフィルタパネル（左ペイン埋め込み用）。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .video_cluster_db import VideoClusterDB


class TagFilterPanel(QWidget):
    """タグをチェックボックスで表示し、フィルタ変更をシグナルで通知する。

    Signals:
        filter_changed(list[str]): 選択中のタグリスト。空リストはフィルタ解除。
    """

    filter_changed = Signal(list)

    def __init__(self, db: Optional[VideoClusterDB] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._checks: dict[str, QCheckBox] = {}
        self._folder_prefix = ""
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ヘッダー
        header = QFrame()
        header.setObjectName("tagFilterHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(0)

        title_row_layout = QVBoxLayout()
        title_label = QLabel("タグフィルタ")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)

        self._clear_btn = QPushButton("クリア")
        self._clear_btn.setFixedHeight(20)
        self._clear_btn.setStyleSheet("QPushButton { font-size: 11px; padding: 0 4px; }")
        self._clear_btn.clicked.connect(self.clear_filter)

        from PySide6.QtWidgets import QHBoxLayout
        title_row = QHBoxLayout()
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(self._clear_btn)
        header_layout.addLayout(title_row)

        outer.addWidget(header)

        # スクロールエリア（タグ一覧）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMaximumHeight(300)

        self._tag_container = QWidget()
        self._tag_layout = QVBoxLayout(self._tag_container)
        self._tag_layout.setContentsMargins(8, 4, 8, 4)
        self._tag_layout.setSpacing(2)
        self._tag_layout.addStretch()

        scroll.setWidget(self._tag_container)
        outer.addWidget(scroll, 1)

        self._empty_label = QLabel("（タグなし — 動画をスキャンしてください）")
        self._empty_label.setStyleSheet("color: #808080; font-size: 11px;")
        self._empty_label.setWordWrap(True)
        self._tag_layout.insertWidget(0, self._empty_label)

    def set_db(self, db: VideoClusterDB) -> None:
        self._db = db
        self.refresh(self._folder_prefix)

    def refresh(self, folder_prefix: str = "") -> None:
        """DB からタグ一覧を再読み込みしてUIを更新する。"""
        self._folder_prefix = folder_prefix
        self._rebuild_tags()

    def _rebuild_tags(self) -> None:
        # 既存チェックボックスのみ削除（_empty_label / stretch は残す）
        for cb in list(self._checks.values()):
            self._tag_layout.removeWidget(cb)
            cb.deleteLater()
        self._checks.clear()

        if self._db is None:
            self._empty_label.setVisible(True)
            return

        tags = self._db.get_all_tags_with_counts(self._folder_prefix)
        if not tags:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)
        for t in tags:
            tag = t["canonical_tag"]
            cnt = t["cnt"]
            cb = QCheckBox(f"{tag}  ({cnt})")
            cb.setProperty("tag_name", tag)
            cb.stateChanged.connect(self._on_check_changed)
            self._tag_layout.insertWidget(self._tag_layout.count() - 1, cb)
            self._checks[tag] = cb

    def _on_check_changed(self, _state) -> None:
        active = [tag for tag, cb in self._checks.items() if cb.isChecked()]
        self.filter_changed.emit(active)

    def clear_filter(self) -> None:
        for cb in self._checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.filter_changed.emit([])

    def selected_tags(self) -> list[str]:
        return [tag for tag, cb in self._checks.items() if cb.isChecked()]
