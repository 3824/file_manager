import os
import sys
from PySide6.QtWidgets import QTreeView, QStyle, QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtCore import Qt, QMimeData, QUrl, QFileInfo, QRect, Signal, QObject
from PySide6.QtGui import QDrag, QColor, QPalette, QFont, QFontMetrics, QPainter

class FileListView(QTreeView):
    """ファイル一覧用のドラッグ対応ビュー。"""

    DRAG_MIME_TYPE = "application/x-file-manager-selected-paths"
    middle_clicked = Signal(object)  # QModelIndex

    def __init__(self, file_manager, parent=None):
        super().__init__(parent)
        self.file_manager = file_manager
        self.setUniformRowHeights(True)

    def startDrag(self, supported_actions):
        """選択中のファイルパスをドラッグデータとして開始する。"""
        selected_paths = self.file_manager._get_selected_paths()
        if not selected_paths:
            return

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(path) for path in selected_paths])
        mime_data.setData(
            self.DRAG_MIME_TYPE,
            "\n".join(selected_paths).encode("utf-8"),
        )

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                self.middle_clicked.emit(idx)
            event.accept()
            return
        super().mousePressEvent(event)

class _SplitterCollapseFilter(QObject):
    """スプリッターハンドルをダブルクリックして左ペインを折りたたむ / 復元するフィルター。"""

    _DEFAULT_LEFT_WIDTH = 300

    def __init__(self, splitter):
        super().__init__(splitter)
        self._splitter = splitter
        self._prev_sizes = []

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonDblClick:
            sizes = self._splitter.sizes()
            if sizes and sizes[0] == 0:
                # 折りたたみ状態から復元
                restore = self._prev_sizes if (self._prev_sizes and self._prev_sizes[0] > 0) else None
                if restore:
                    self._splitter.setSizes(restore)
                else:
                    total = sum(sizes)
                    self._splitter.setSizes([self._DEFAULT_LEFT_WIDTH, max(0, total - self._DEFAULT_LEFT_WIDTH)])
            else:
                # 折りたたむ
                self._prev_sizes = list(sizes)
                total = sum(sizes)
                self._splitter.setSizes([0, total])
            return True
        return super().eventFilter(obj, event)

class FileItemDelegate(QStyledItemDelegate):
    """ファイル属性に基づいてアイテムの表示を変更するカスタムデリゲート"""

    def __init__(self, file_manager, parent=None):
        super().__init__(parent)
        self.file_manager = file_manager

    def paint(self, painter, option, index):
        """アイテムの描画"""
        option_copy = QStyleOptionViewItem(option)
        self.initStyleOption(option_copy, index)

        color_override = None
        model = index.model()
        file_path = None
        folder_model = None
        # file_manager が必要なモデル属性を持っているかチェック
        if hasattr(self.file_manager, 'file_system_model') and hasattr(self.file_manager, 'left_pane'):
            # LeftPaneWidget のフォルダモデル取得
            if hasattr(self.file_manager.left_pane, 'folder_model'):
                folder_model = self.file_manager.left_pane.folder_model

            if hasattr(model, 'mapToSource'):
                source_index = model.mapToSource(index)
                file_path = self.file_manager.file_system_model.filePath(source_index)
            elif folder_model is not None and model == folder_model:
                file_path = folder_model.filePath(index)
            elif model == self.file_manager.file_system_model:
                file_path = self.file_manager.file_system_model.filePath(index)

            if file_path:
                file_info = QFileInfo(file_path)
                if file_info.exists():
                    color_override = self.get_file_color(file_info)

        if color_override is not None:
            # 属性色設定を取得。存在しない場合のフォールバック
            candidate_color = QColor(color_override)
            if candidate_color.isValid() and not (option_copy.state & QStyle.State_Selected):
                for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                    option_copy.palette.setColor(group, QPalette.Text, candidate_color)

        # サイズバッジ計算（テキスト領域と重複しないよう先にサイズを確保）
        size_text = None
        badge_rect = None
        is_folder_item = (
            file_path
            and folder_model is not None
            and model == folder_model
            and hasattr(self.file_manager, 'left_pane')
        )
        if is_folder_item:
            sizes = getattr(self.file_manager.left_pane, 'folder_sizes', {})
            if file_path in sizes:
                size_val = sizes[file_path]
                size_text = "···" if size_val is None else self._format_size(size_val)

        if size_text:
            badge_font = QFont(painter.font())
            badge_font.setPixelSize(10)
            fm = QFontMetrics(badge_font)
            badge_w = fm.horizontalAdvance(size_text) + 12
            badge_h = 16
            badge_x = option.rect.right() - badge_w - 5
            badge_y = option.rect.top() + (option.rect.height() - badge_h) // 2
            badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)
            # バッジ分だけテキスト描画領域を縮小してフォルダ名との重複を防ぐ
            option_copy.rect = option.rect.adjusted(0, 0, -(badge_w + 10), 0)

        # 切り取り中アイテムは半透明で描画
        is_cut = (
            file_path
            and getattr(self.file_manager, '_clipboard_move', False)
            and file_path in getattr(self.file_manager, '_clipboard_paths', [])
        )
        if is_cut:
            painter.save()
            painter.setOpacity(0.4)
        try:
            super().paint(painter, option_copy, index)

            # サイズバッジを描画
            if size_text and badge_rect:
                is_selected = bool(option.state & QStyle.State_Selected)
                is_calculating = (size_text == "···")

                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)

                if is_selected:
                    bg = QColor(56, 189, 248, 45)
                    fg = QColor(14, 165, 233)
                elif is_calculating:
                    bg = QColor(148, 163, 184, 28)
                    fg = QColor(148, 163, 184)
                else:
                    bg = QColor(100, 116, 139, 28)
                    fg = QColor(100, 116, 139)

                painter.setPen(Qt.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(badge_rect, badge_rect.height() / 2, badge_rect.height() / 2)

                badge_font = QFont(painter.font())
                badge_font.setPixelSize(10)
                badge_font.setWeight(QFont.Weight.Medium)
                painter.setFont(badge_font)
                painter.setPen(fg)
                painter.drawText(badge_rect, Qt.AlignCenter, size_text)

                painter.restore()
        finally:
            if is_cut:
                painter.restore()

    @staticmethod
    def _format_size(byte_count: int) -> str:
        size = float(max(0, byte_count))
        units = ("B", "KB", "MB", "GB", "TB", "PB")
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} B"
                return f"{size:.1f} {unit}"
            size /= 1024.0

    def get_file_color(self, file_info):
        """ファイル属性に基づいて色を決定"""
        colors = getattr(self.file_manager, 'attribute_colors', {})
        
        # 隠しファイルかチェック
        if file_info.fileName().startswith('.') and file_info.fileName() not in ['.', '..']:
            return colors.get("hidden", "#808080")

        # Windowsの場合の隠しファイル属性チェック
        if sys.platform == "win32":
            import stat
            try:
                file_stat = os.stat(file_info.filePath())
                if file_stat.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN:
                    return colors.get("hidden", "#808080")
                if file_stat.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM:
                    return colors.get("system", "#FF0000")
            except (AttributeError, OSError):
                pass

        # 読み込み専用ファイルかチェック
        if not file_info.isWritable() and file_info.isReadable():
            return colors.get("readonly", "#0000FF")

        # デフォルト色
        return colors.get("normal", "#000000")
