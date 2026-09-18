import os
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QProgressBar,
    QTreeView, QPushButton, QButtonGroup, QSizePolicy, QHeaderView, QMessageBox,
    QFileSystemModel
)
from PySide6.QtCore import Qt, QDir, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont
from .views import FileListView
from .logger import logger

try:
    # video_cluster_db のインポートに失敗した場合はフィルタパネルも無効化する
    # (file_manager.py の VIDEO_CLUSTER_AVAILABLE と同じ判定基準を保つため)
    from .video_cluster_db import VideoClusterDB as _VideoClusterDB  # noqa: F401
    from .video_cluster_filter import TagFilterPanel
    _TAG_FILTER_AVAILABLE = True
except Exception:
    TagFilterPanel = None  # type: ignore
    _TAG_FILTER_AVAILABLE = False


def _format_folder_size(byte_count: int) -> str:
    """バイト数を人間が読みやすい文字列に変換する。"""
    size = float(max(0, byte_count))
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0


def _calculate_folder_size(path: str, should_stop=None) -> int:
    """フォルダ配下のファイルサイズ合計を再帰的に返す。

    os.scandir() を使って DirEntry.stat() のキャッシュを活用し、
    os.path.getsize() の個別 stat 呼び出しを削減している。
    """
    if not path or not os.path.isdir(path):
        return 0

    should_stop = should_stop or (lambda: False)
    total = 0
    stack = [path]
    while stack:
        if should_stop():
            return total
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if should_stop():
                        return total
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        pass
        except (OSError, PermissionError):
            pass
    return total


def _get_volume_info(drive_letter: str):
    """ドライブのボリューム名・使用率・空き・合計バイトを返す。"""
    label = ""
    ratio = 0.0
    free = 0
    total = 0
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(
                f"{drive_letter}:\\", buf, 261, None, None, None, None, 0
            )
            label = buf.value or ""
        except Exception:
            pass
        try:
            import shutil
            usage = shutil.disk_usage(f"{drive_letter}:\\")
            total = usage.total
            free = usage.free
            ratio = (total - free) / total if total > 0 else 0.0
        except Exception:
            pass
    return label, ratio, free, total


class DriveButton(QPushButton):
    """ドライブレター・ボリューム名・使用量バーを表示するカスタムボタン。"""

    BTN_H = 32

    def __init__(self, drive_letter: str, parent=None):
        super().__init__(f"{drive_letter}:", parent)
        self.drive_letter = drive_letter
        self.volume_label, self.usage_ratio, self._free, self._total = _get_volume_info(drive_letter)
        self.setCheckable(True)
        self.setFixedHeight(self.BTN_H)
        self.setMinimumWidth(36)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip(self._build_tooltip())

    def _build_tooltip(self) -> str:
        parts = [f"ドライブ {self.drive_letter}:"]
        if self.volume_label:
            parts.append(f"ラベル: {self.volume_label}")
        if self._total > 0:
            free_str = _format_folder_size(self._free)
            total_str = _format_folder_size(self._total)
            parts.append(f"空き: {free_str} / 合計: {total_str}  ({self.usage_ratio * 100:.0f}% 使用中)")
        return "\n".join(parts)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.usage_ratio <= 0:
            return
        painter = QPainter(self)
        r = self.rect()
        bar_h = 2
        bar_x = r.left() + 3
        bar_y = r.bottom() - bar_h
        bar_w = r.width() - 6
        if bar_w > 0:
            fill_w = int(bar_w * min(1.0, self.usage_ratio))
            if fill_w > 0:
                if self.usage_ratio > 0.9:
                    fill_color = QColor("#EF4444")
                elif self.usage_ratio > 0.7:
                    fill_color = QColor("#F59E0B")
                else:
                    fill_color = QColor("#7DD3FC") if self.isChecked() else QColor("#818CF8")
                painter.setPen(Qt.NoPen)
                painter.setBrush(fill_color)
                painter.drawRect(bar_x, bar_y, fill_w, bar_h)
        painter.end()


class FolderSizeWorker(QThread):
    """フォルダサイズをバックグラウンドで計算するワーカー。"""

    size_calculated = Signal(str, int)  # (path, bytes)

    def __init__(self):
        super().__init__(None)  # parent=None: Qt の親子破壊を受けない
        self._path = ""
        self._stop_flag = False

    def start_for(self, path: str) -> None:
        """指定パスのサイズ計算を開始する。実行中なら停止後に再起動。"""
        self._stop_flag = True
        if self.isRunning():
            if not self.wait(400):
                return  # 停止できなければスキップ
        self._path = path
        self._stop_flag = False
        self.start()

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        path = self._path
        try:
            total = _calculate_folder_size(path, lambda: self._stop_flag)
        except OSError:
            total = 0
        if not self._stop_flag:
            self.size_calculated.emit(path, total)


class FolderTreeView(QTreeView):
    """左ペイン用のドロップ受付ツリー。"""

    files_dropped = Signal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def drawBranches(self, painter, rect, index):
        """カスタム三角矢印で展開/折りたたみインジケーターを描画する。"""
        model = self.model()
        if model is None:
            return

        has_children = model.hasChildren(index)
        is_expanded = self.isExpanded(index)

        if has_children:
            s = 4.5
            cx = float(rect.right() - 11)
            cy = float(rect.center().y())

            path = QPainterPath()
            if is_expanded:
                path.moveTo(cx - s, cy - s * 0.4)
                path.lineTo(cx + s, cy - s * 0.4)
                path.lineTo(cx,     cy + s * 0.8)
            else:
                path.moveTo(cx - s * 0.4, cy - s)
                path.lineTo(cx + s * 0.8, cy)
                path.lineTo(cx - s * 0.4, cy + s)
            path.closeSubpath()

            sm = self.selectionModel()
            is_selected = sm is not None and sm.isSelected(index)
            arrow_color = QColor(56, 189, 248, 220) if is_selected else QColor(148, 163, 184, 160)

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(arrow_color)
            painter.drawPath(path)
            painter.restore()

    def dragEnterEvent(self, event):
        if self._extract_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._extract_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._extract_paths(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        target_path = self._resolve_drop_target(event.position().toPoint())
        if not target_path:
            event.ignore()
            return
        self.files_dropped.emit(paths, target_path)
        event.acceptProposedAction()

    def _resolve_drop_target(self, position):
        index = self.indexAt(position)
        if index.isValid() and self.model() is not None and hasattr(self.model(), "filePath"):
            path = self.model().filePath(index)
            if os.path.isdir(path):
                return path
            return os.path.dirname(path)
        root_index = self.rootIndex()
        if root_index.isValid() and self.model() is not None and hasattr(self.model(), "filePath"):
            path = self.model().filePath(root_index)
            if os.path.isdir(path):
                return path
        return None

    @staticmethod
    def _extract_paths(mime_data):
        if mime_data is None:
            return []
        if mime_data.hasFormat(FileListView.DRAG_MIME_TYPE):
            payload = bytes(mime_data.data(FileListView.DRAG_MIME_TYPE)).decode("utf-8")
            return [path for path in payload.splitlines() if path]
        if mime_data.hasUrls():
            return [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]
        return []


class LeftPaneWidget(QWidget):
    """左ペインウィジェット（ドライブボタン + フォルダツリー）"""

    drive_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_drive = None
        self.drive_buttons = {}
        self.drive_button_group = QButtonGroup(self)
        self.drive_button_group.setExclusive(True)
        # path -> size bytes (None = 計算中, int = 計算済み)
        self.folder_sizes: dict = {}
        self._size_workers: dict[str, FolderSizeWorker] = {}
        self._initial_load_done = False
        self._pending_root_path = ""
        self._current_root_path = ""
        self.init_ui()
        self.setup_folder_tree()
        self.setup_drive_buttons()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.drive_frame = QFrame()
        self.drive_frame.setObjectName("driveBar")
        self.drive_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.drive_frame.setMinimumHeight(44)
        drive_layout = QHBoxLayout(self.drive_frame)
        drive_layout.setContentsMargins(12, 4, 12, 4)
        drive_layout.setSpacing(6)

        self.drive_container = QWidget()
        self.drive_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.drive_buttons_layout = QHBoxLayout(self.drive_container)
        self.drive_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.drive_buttons_layout.setSpacing(4)

        drive_layout.addWidget(self.drive_container)
        drive_layout.addStretch()

        layout.addWidget(self.drive_frame, 0)

        self.tree_frame = QFrame()
        self.tree_frame.setObjectName("treePanel")
        self.tree_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tree_layout = QVBoxLayout(self.tree_frame)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        self.tree_header = QLabel("FOLDERS")
        self.tree_header.setObjectName("foldersLabel")
        self.tree_header.setMinimumHeight(34)
        self.tree_header.setContentsMargins(0, 0, 0, 0)
        self.tree_header.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tree_layout.addWidget(self.tree_header, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(20)
        tree_layout.addWidget(self.progress_bar, 0)

        self.tree_view = FolderTreeView()
        self.tree_view.setObjectName("folderTree")
        self.tree_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setRootIsDecorated(True)
        self.tree_view.setAlternatingRowColors(False)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(18)
        self.tree_view.setSortingEnabled(False)
        self.tree_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_view.setExpandsOnDoubleClick(True)

        tree_layout.addWidget(self.tree_view, 1)
        layout.addWidget(self.tree_frame, 1)

        # タグフィルタパネル（動画クラスタリング）
        self.tag_filter: "TagFilterPanel | None" = None
        if _TAG_FILTER_AVAILABLE and TagFilterPanel is not None:
            self.tag_filter = TagFilterPanel()
            layout.addWidget(self.tag_filter, 0)

        layout.setStretchFactor(self.drive_frame, 0)
        layout.setStretchFactor(self.tree_frame, 1)

    def take_drive_widget(self):
        return None

    def setup_drive_buttons(self):
        for button in list(self.drive_buttons.values()):
            self.drive_buttons_layout.removeWidget(button)
            self.drive_button_group.removeButton(button)
            button.deleteLater()
        self.drive_buttons.clear()

        available_drives = self.get_available_drives()

        for drive in available_drives:
            button = DriveButton(drive)
            self.drive_button_group.addButton(button)
            button.clicked.connect(lambda checked, d=drive: self.on_drive_selected(d))
            self.drive_buttons[drive] = button
            self.drive_buttons_layout.addWidget(button)

        if available_drives:
            first = available_drives[0]
            self._update_drive_button_state(first)
            self.current_drive = first
            # showEvent で実際の読み込みを行う（タイマー不使用）

    def _update_drive_button_state(self, drive: str | None) -> None:
        for btn_drive, button in self.drive_buttons.items():
            button.setChecked(btn_drive == drive)

    def get_available_drives(self):
        drives = []
        if sys.platform == "win32":
            import string
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    drives.append(letter)
        else:
            drives = ["/"]
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            mount_point = parts[1]
                            if mount_point.startswith('/') and mount_point != '/':
                                drives.append(mount_point)
            except Exception as e:
                logger.debug(f"Failed to read /proc/mounts: {e}")
        return drives

    def setup_folder_tree(self):
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath("")
        self.folder_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.folder_model.directoryLoaded.connect(self._on_directory_loaded)

        self.tree_view.setModel(self.folder_model)
        self.tree_view.clicked.connect(self._on_tree_item_clicked)

        header = self.tree_view.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setMinimumSectionSize(100)
        header.setDefaultSectionSize(200)

        for i in range(1, self.folder_model.columnCount()):
            self.tree_view.hideColumn(i)

    def showEvent(self, event) -> None:
        """初回表示時にドライブルートを読み込む。"""
        super().showEvent(event)
        if not self._initial_load_done and self.current_drive:
            self._initial_load_done = True
            self._apply_drive_root(self.current_drive)

    def _apply_drive_root(self, drive: str) -> None:
        """指定ドライブをツリーのルートとして設定する。"""
        if sys.platform == "win32":
            drive_path = f"{drive}:\\"
        else:
            drive_path = drive
        self._apply_tree_root_path(drive_path)

    def _apply_tree_root_path(self, root_path: str) -> None:
        """QFileSystemModel に root_path を読み込ませ、ツリーへ反映する。"""
        if not hasattr(self, 'folder_model'):
            return
        if not root_path or not os.path.exists(root_path):
            return

        normalized_root = os.path.normcase(os.path.abspath(root_path))
        if self._current_root_path == normalized_root:
            root_index = self.folder_model.index(root_path)
            if root_index.isValid():
                self.tree_view.setRootIndex(root_index)
            return

        self._pending_root_path = normalized_root
        self._current_root_path = normalized_root
        root_index = self.folder_model.setRootPath(root_path)
        if not root_index.isValid():
            root_index = self.folder_model.index(root_path)

        if root_index.isValid():
            self.tree_view.setRootIndex(root_index)
            if self.folder_model.canFetchMore(root_index):
                self.folder_model.fetchMore(root_index)
        # directoryLoaded シグナルで表示を更新する（タイマーによるリトライは行わない）

    def _on_directory_loaded(self, path: str) -> None:
        """ディレクトリ読み込み完了時にルートインデックスを更新する。"""
        if not self._pending_root_path:
            return
        loaded = os.path.normcase(os.path.abspath(path))
        if loaded != self._pending_root_path:
            return
        root_index = self.folder_model.index(path)
        if root_index.isValid():
            self.tree_view.setRootIndex(root_index)
            if self.folder_model.canFetchMore(root_index):
                self.folder_model.fetchMore(root_index)

    def _on_tree_item_clicked(self, index) -> None:
        """クリックされたフォルダのサイズ計算をリクエストする。"""
        if not index.isValid():
            return
        path = self.folder_model.filePath(index)
        if not os.path.isdir(path):
            return
        if path in self.folder_sizes and self.folder_sizes[path] is None:
            return  # 計算中
        self.folder_sizes[path] = None  # 計算中マーク
        self.tree_view.update(index)  # "..." を表示するため再描画
        worker = FolderSizeWorker()
        self._size_workers[path] = worker
        worker.size_calculated.connect(self._on_size_calculated)
        worker.finished.connect(lambda p=path: self._on_size_worker_finished(p))
        worker.start_for(path)

    def _on_size_calculated(self, path: str, byte_count: int) -> None:
        """ワーカーからサイズ計算結果を受け取る。"""
        self.folder_sizes[path] = byte_count
        # 該当アイテムを再描画してサイズを表示
        idx = self.folder_model.index(path)
        if idx.isValid():
            self.tree_view.update(idx)

    def _on_size_worker_finished(self, path: str) -> None:
        worker = self._size_workers.pop(path, None)
        if worker is not None:
            worker.deleteLater()
        # 計算中マーク (None) が残っている場合（キャンセル等）は未取得を示す -1 に更新して再描画
        if self.folder_sizes.get(path) is None:
            self.folder_sizes.pop(path, None)
            idx = self.folder_model.index(path)
            if idx.isValid():
                self.tree_view.update(idx)

    def show_progress(self, message: str = "読み込み中...") -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat(message)
        self.tree_view.setEnabled(False)
        for button in self.drive_buttons.values():
            button.setEnabled(False)

    def hide_progress(self) -> None:
        self.progress_bar.setVisible(False)
        self.tree_view.setEnabled(True)
        for button in self.drive_buttons.values():
            button.setEnabled(True)

    def on_drive_selected(self, drive: str) -> None:
        self._update_drive_button_state(drive)
        self.select_drive_async(drive)

    def select_drive_async(self, drive: str) -> None:
        self.current_drive = drive
        self._update_drive_button_state(drive)
        if sys.platform == "win32":
            drive_path = f"{drive}:\\"
        else:
            drive_path = drive
        self.show_progress(f"ドライブ {drive} を読み込み中...")
        QTimer.singleShot(100, lambda: self.load_drive_sync(drive_path))

    def load_drive_sync(self, drive_path: str) -> None:
        try:
            if not os.path.exists(drive_path):
                raise FileNotFoundError(f"ドライブが見つかりません: {drive_path}")
            # ドライブ文字を逆引きして _apply_drive_root を使う
            if sys.platform == "win32":
                drive_letter = drive_path.rstrip("\\").rstrip(":")
            else:
                drive_letter = drive_path
            self._apply_drive_root(drive_letter)
            self._update_drive_button_state(self.current_drive)
            self.hide_progress()
            self.drive_selected.emit(self.current_drive)
        except Exception as e:
            logger.error(f"Error loading drive {drive_path}: {e}")
            self.hide_progress()
            QMessageBox.warning(self, "エラー", f"ドライブの読み込みに失敗しました:\n{str(e)}")

    def select_drive(self, drive: str) -> None:
        self._update_drive_button_state(drive)
        self.current_drive = drive
        self._apply_drive_root(drive)

    def get_selected_path(self) -> str | None:
        if not hasattr(self, 'folder_model'):
            return None
        current_index = self.tree_view.currentIndex()
        if current_index.isValid():
            return self.folder_model.filePath(current_index)
        return None

    def cleanup_worker(self) -> None:
        """ワーカースレッドを停止してリソースを解放する。"""
        for worker in list(self._size_workers.values()):
            worker.stop()
            if worker.isRunning():
                worker.wait(2000)
                if worker.isRunning():
                    worker.terminate()
                    worker.wait(1000)
            worker.deleteLater()
        self._size_workers.clear()
