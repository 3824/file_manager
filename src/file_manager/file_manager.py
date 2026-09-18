#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイルマネージャーのメインウィジェット
"""

import os
import shutil
import stat
import string
import sys
from functools import partial
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QSplitter,
    QHeaderView, QMessageBox, QInputDialog, QMenu, QAbstractItemView,
    QToolBar, QComboBox, QLineEdit, QPushButton, QDialog, QCheckBox,
    QLabel, QFrame, QProgressBar, QSizePolicy, QStyle, QStackedWidget,
    QColorDialog,
)
from PySide6.QtCore import (
    Qt, QDir, QTimer, QSettings, QFileInfo, QObject, QEvent, Signal, QItemSelectionModel
)
from PySide6.QtGui import QAction, QKeySequence, QFont, QColor, QPalette, QShortcut

try:
    from .ui_theme import apply_theme as _apply_ui_theme
    _UI_THEME_AVAILABLE = True
except Exception:
    _UI_THEME_AVAILABLE = False

# 動画ダイジェスト関連のインポート
try:
    from .video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
    from .video_digest_dialog import VideoDigestDialog
    VIDEO_DIGEST_AVAILABLE = True
except ImportError:
    VIDEO_DIGEST_AVAILABLE = False
    OPENCV_AVAILABLE = False
    VideoDigestGenerator = None  # type: ignore
    VideoDigestDialog = None  # type: ignore

from .video_thumbnail_preview import VideoThumbnailPreview

try:
    from .video_player_window import VideoPlayerWindow
    VIDEO_PLAYER_AVAILABLE = True
except Exception:
    VideoPlayerWindow = None  # type: ignore
    VIDEO_PLAYER_AVAILABLE = False

# ファイル検索関連のインポート
try:
    from .file_search_dialog import FileSearchDialog
    FILE_SEARCH_AVAILABLE = True
except ImportError:
    FILE_SEARCH_AVAILABLE = False

# ディスク分析関連のインポート
try:
    from .disk_analysis_dialog import DiskAnalysisDialog
    DISK_ANALYSIS_AVAILABLE = True
except ImportError:
    DISK_ANALYSIS_AVAILABLE = False

# 動画重複検出関連のインポート
try:
    from .video_duplicates_dialog import VideoDuplicatesDialog
    VIDEO_DUPLICATES_AVAILABLE = True
except ImportError:
    VIDEO_DUPLICATES_AVAILABLE = False
    VideoDuplicatesDialog = None  # type: ignore

# ファイル名類似度検出関連のインポート
try:
    from .filename_similarity_dialog import FilenameSimilarityDialog
    FILENAME_SIMILARITY_AVAILABLE = True
except ImportError:
    FILENAME_SIMILARITY_AVAILABLE = False
    FilenameSimilarityDialog = None  # type: ignore

try:
    from .filename_translation import (
        FilenameTranslationService,
        TRANSLATION_API_ENV_KEY,
    )
    from .translate_preview_dialog import TranslatePreviewDialog
    TRANSLATION_FEATURE_AVAILABLE = True
except ImportError:
    FilenameTranslationService = None  # type: ignore
    TranslatePreviewDialog = None  # type: ignore
    TRANSLATION_API_ENV_KEY = "TRANSLATION_API_KEY"
    TRANSLATION_FEATURE_AVAILABLE = False

# 同じファイルサイズ検出関連のインポート
try:
    from .same_filesize_dialog import SameFileSizeDialog
    SAME_FILESIZE_AVAILABLE = True
except ImportError:
    SAME_FILESIZE_AVAILABLE = False
    SameFileSizeDialog = None  # type: ignore

try:
    from .video_digest_cache import VideoDigestCache
except ImportError:
    VideoDigestCache = None  # type: ignore

# 動画クラスタリング関連のインポート
try:
    from .video_cluster_db import VideoClusterDB
    from .video_cluster_dialog import VideoClusterScanDialog, VideoClusterBrowserDialog
    VIDEO_CLUSTER_AVAILABLE = True
except Exception:
    VideoClusterDB = None  # type: ignore
    VideoClusterScanDialog = None  # type: ignore
    VideoClusterBrowserDialog = None  # type: ignore
    VIDEO_CLUSTER_AVAILABLE = False


from .logger import logger
from .qt_models import RenameSummary, CustomFileSystemModel, FileSortFilterProxyModel, VideoMetadataWorker
from .views import FileListView, FileItemDelegate, _SplitterCollapseFilter
from .left_pane import LeftPaneWidget
from .settings_dialog import SettingsDialog
from .utils import coerce_bool, coerce_int, coerce_str, coerce_color, silent_question, silent_warning, silent_information
from .constants import TOOLBAR_ALL_ITEMS, TOOLBAR_DEFAULT_ORDER, normalize_toolbar_order


def _rename_file_without_overwrite(source: Path, target: Path) -> None:
    """既存ファイルを上書きせず、同じディレクトリ内で名前を変更する。"""
    source = Path(source)
    target = Path(target)
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target)):
        return
    if os.path.lexists(target):
        raise FileExistsError(f"同名ファイルが既に存在します: {target.name}")

    if os.name == "nt":
        # Windows の os.rename は既存の宛先を上書きしない。
        os.rename(source, target)
        return

    # POSIX の os.rename は上書きするため、ハードリンク作成の排他性を利用する。
    os.link(source, target, follow_symlinks=False)
    try:
        os.unlink(source)
    except Exception:
        os.unlink(target)
        raise


class FileManagerWidget(QWidget):
    COLUMN_WIDTHS_KEY = "column_widths"
    DETAIL_VIEW_COLUMNS = [
        ("name", 0),
        ("size", 1),
        ("type", 2),
        ("modified", 3),
        ("permissions", 4),
        ("created", 5),
        ("attributes", 6),
        ("extension", 7),
        ("owner", 8),
        ("group", 9),
        ("duration", 10),
        ("resolution", 11),
        ("fps", 12),
    ]

    # ステータスバーなど外部コンポーネントへの選択変化通知
    selection_changed = Signal()

    DEFAULT_COLUMN_WIDTHS = {
        "name": 260,
        "size": 120,
        "type": 140,
        "modified": 170,
        "permissions": 160,
        "created": 170,
        "attributes": 180,
        "extension": 110,
        "owner": 160,
        "group": 160,
        "duration": 100,
        "resolution": 100,
        "fps": 60,
    }

    def __init__(self, parent=None):
        self._owns_app = False
        self._owned_qapplication = None
        self._qt_available = isinstance(QApplication, type)

        if self._qt_available:
            app_instance = QApplication.instance()
            if app_instance is None:
                if (
                    sys.platform.startswith("linux")
                    and not os.environ.get("DISPLAY")
                    and not os.environ.get("WAYLAND_DISPLAY")
                    and not os.environ.get("QT_QPA_PLATFORM")
                ):
                    os.environ["QT_QPA_PLATFORM"] = "offscreen"

                argv = sys.argv if len(sys.argv) > 0 else [""]
                QApplication(argv)
                self._owns_app = True
                app_instance = QApplication.instance()

            self._owned_qapplication = app_instance
            super().__init__(parent)
        else:
            pass

        if not self._owned_qapplication and self._qt_available:
            self._owned_qapplication = QApplication.instance()

        self.current_path = QDir.homePath()
        self.settings = self._create_settings()
        self.view_mode = "list"
        self.show_hidden = True
        self.visible_columns = {
            "name": True,
            "size": True,
            "type": True,
            "modified": True,
            "permissions": False,
            "created": False,
            "attributes": True,
            "extension": False,
            "owner": False,
            "group": False,
            "duration": True,
            "resolution": True,
            "fps": False
        }
        self.attribute_colors = {
            "hidden": "#808080",
            "readonly": "#0000FF",
            "system": "#FF0000",
            "normal": "#000000"
        }
        self.worker_thread = None
        self.worker = None
        self._nav_history: list[str] = []
        self._nav_forward_stack: list[str] = []
        self._nav_jumping = False
        self._syncing_left_pane = False
        self._clipboard_paths: list[str] = []
        self._clipboard_move = False

        self.thread_pool = None
        self.metadata_worker = None
        self.video_digest_generator = None
        self._opencv_warning_shown = False
        self.thumbnail_preview = None

        # 動画クラスタリング
        self._cluster_db: "VideoClusterDB | None" = None
        self._active_tag_filter: list[str] = []
        self.video_thumbnail_count = 6
        self.video_thumbnail_size = (160, 90)
        self.video_auto_show_digest = False
        self.video_digest_trigger = "none"
        self.video_hover_thumbnail_enabled = False
        self.video_digest_max_frames = 12
        self.video_digest_cache_size_mb = 200
        self.video_player_enabled = True
        self.video_player_default_speed = 1.0
        self.video_player_default_muted = True
        self.video_player_autoplay = True
        self._video_player_window = None
        self.filter_foreign_filenames = False

        self.load_settings()

        try:
            last_path = self.settings.value("last_path", "", type=str)
            if last_path and os.path.isdir(last_path):
                self.current_path = last_path
        except Exception as e:
            logger.debug(f"Failed to load last_path: {e}")
        
        if self._qt_available:
            self.init_ui()
            self.setup_models()
            self.connect_signals()
            self.setup_context_menus()
            self.setup_custom_delegate()
            self._setup_shortcuts()
            self.load_settings()

            try:
                self.setup_detail_view()
            except Exception as e:
                logger.error(f"Failed to setup detail view: {e}")

            self._restore_splitter_state()

            try:
                restore_path = self.settings.value("last_path", "", type=str)
                if restore_path and os.path.isdir(restore_path):
                    if sys.platform == "win32" and hasattr(self, 'left_pane'):
                        drive, _ = os.path.splitdrive(restore_path)
                        if drive:
                            self.left_pane.select_drive(drive.rstrip(":"))
                    self.set_current_path(restore_path)
            except Exception as e:
                logger.debug(f"Failed to restore path on startup: {e}")

    def apply_settings(self):
        """エイリアス: テスト互換のため"""
        return self.load_settings()

    def apply_fonts(self):
        """QSettings のフォント設定を左ペインとリストビューに適用する"""
        try:
            s = self.settings
            tree_family = coerce_str(s.value("tree_font_family", ""), "")
            tree_size = coerce_int(s.value("tree_font_size", 10), 10, minimum=8, maximum=24)
            list_family = coerce_str(s.value("list_font_family", ""), "")
            list_size = coerce_int(s.value("list_font_size", 10), 10, minimum=8, maximum=24)
            if tree_family and hasattr(self, 'left_pane') and hasattr(self.left_pane, 'tree_view'):
                self.left_pane.tree_view.setFont(QFont(tree_family, tree_size))
            if list_family and hasattr(self, 'list_view'):
                self.list_view.setFont(QFont(list_family, list_size))
        except Exception as e:
            logger.error(f"Apply fonts error: {e}")

    def _on_metadata_ready(self, path: str, info: dict) -> None:
        """動画メタデータ取得完了時の処理"""
        if hasattr(self, 'file_system_model'):
            self.file_system_model.update_metadata(path, info)

    def _get_video_digest_generator(self):
        """動画ダイジェスト生成器を必要時に生成して返す。"""
        if not VIDEO_DIGEST_AVAILABLE:
            return None
        if self.video_digest_generator is None:
            self.video_digest_generator = VideoDigestGenerator()
        return self.video_digest_generator

    def _is_video_file(self, path: str) -> bool:
        """動画ファイル判定を共通化する。"""
        generator = self._get_video_digest_generator()
        if generator:
            return bool(generator.is_video_file(path))
        video_extensions = {
            ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv",
            ".webm", ".m4v", ".3gp", ".mpg", ".mpeg",
        }
        return bool(path and os.path.isfile(path) and Path(path).suffix.lower() in video_extensions)

    def _ensure_metadata_worker(self) -> bool:
        """動画メタデータ取得ワーカーを必要時に初期化する。"""
        if not VIDEO_DIGEST_AVAILABLE:
            return False
        if self.thread_pool is None:
            from PySide6.QtCore import QThreadPool
            self.thread_pool = QThreadPool()
            self.thread_pool.setMaxThreadCount(2)  # 動画メタデータ取得は 2 スレッドまで
        if self.metadata_worker is None:
            worker = VideoMetadataWorker()
            worker.metadata_ready.connect(self._on_metadata_ready)
            self.metadata_worker = worker
        return True

    def _request_metadata_fetch(self, path: str) -> None:
        """動画メタデータの取得をリクエスト"""
        if not self._ensure_metadata_worker():
            return

        from PySide6.QtCore import QRunnable
        class FetchTask(QRunnable):
            def __init__(self, worker, path):
                super().__init__()
                self.worker = worker
                self.path = path
            def run(self):
                self.worker.fetch_metadata(self.path)
        
        if self.metadata_worker and self.thread_pool:
            task = FetchTask(self.metadata_worker, path)
            self.thread_pool.start(task)

    def cleanup_worker(self):
        """ワーカースレッドのクリーンアップ"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            if not self.worker_thread.wait(3000):
                self.worker_thread.terminate()
                self.worker_thread.wait(3000)
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        
        if self.worker_thread:
            self.worker_thread.deleteLater()
            self.worker_thread = None

        if self.thread_pool is not None:
            self.thread_pool.waitForDone(3000)
            self.thread_pool = None

        self.metadata_worker = None

        if getattr(self, 'thumbnail_preview', None):
            self.thumbnail_preview.shutdown()

        if getattr(self, '_video_player_window', None):
            self._video_player_window.close()
            self._video_player_window = None
    
    def closeEvent(self, event):
        """ウィジェットが閉じられる時のクリーンアップ"""
        self.cleanup_worker()
        if hasattr(self, 'left_pane'):
            self.left_pane.cleanup_worker()
        try:
            self.save_window_state()
        except Exception as e:
            logger.error(f"Failed to save window state: {e}")
        super().closeEvent(event)
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.create_toolbar()

        self.left_pane = LeftPaneWidget()
        self.left_pane.setObjectName("leftPane")
        self.left_pane.setMinimumWidth(200)
        self.left_pane.drive_selected.connect(self.on_drive_selected)

        # ナビゲーションバー
        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12, 4, 12, 4)
        nav_layout.setSpacing(6)

        try:
            from .ui_icons import apply_icon_to_button as _nav_icon
        except ImportError:
            def _nav_icon(btn, name, fallback, **kw):
                btn.setText(fallback)

        self.back_button = QPushButton("‹")
        self.back_button.setObjectName("navBtn")
        self.back_button.setToolTip("戻る (Alt+←)")
        self.back_button.setEnabled(False)
        self.back_button.setFixedSize(28, 28)
        _nav_icon(self.back_button, "nav_back", "‹")
        self.back_button.clicked.connect(self.navigate_back)

        self.forward_button = QPushButton("›")
        self.forward_button.setObjectName("navBtn")
        self.forward_button.setToolTip("進む (Alt+→)")
        self.forward_button.setEnabled(False)
        self.forward_button.setFixedSize(28, 28)
        _nav_icon(self.forward_button, "nav_forward", "›")
        self.forward_button.clicked.connect(self.navigate_forward)

        self.address_bar = QLineEdit()
        self.address_bar.setObjectName("addressBar")
        self.address_bar.setPlaceholderText("パスを入力して Enter...")
        self.address_bar.returnPressed.connect(self.navigate_to_address)
        self.address_bar.installEventFilter(self)

        self.address_stack = QStackedWidget()
        self.address_stack.setObjectName("addressStack")
        self.address_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.breadcrumb_bar = QWidget()
        self.breadcrumb_bar.setObjectName("breadcrumbBar")
        self.breadcrumb_bar.setCursor(Qt.CursorShape.IBeamCursor)
        self.breadcrumb_bar.installEventFilter(self)
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_bar)
        self.breadcrumb_layout.setContentsMargins(6, 2, 6, 2)
        self.breadcrumb_layout.setSpacing(2)

        self.address_stack.addWidget(self.breadcrumb_bar)
        self.address_stack.addWidget(self.address_bar)

        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.forward_button)
        nav_layout.addWidget(self.address_stack, 1)
        layout.addWidget(nav_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        
        self.list_view = FileListView(self)
        self.list_view.setObjectName("fileList")
        self.list_view.setRootIsDecorated(False)
        self.list_view.setAlternatingRowColors(True)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_view.setSortingEnabled(True)
        self.list_view.setHeaderHidden(False)
        self.list_view.setDragEnabled(True)
        self.list_view.setDragDropMode(QAbstractItemView.DragOnly)
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        header = self.list_view.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_column_menu)
        
        self.right_progress_bar = QProgressBar()
        self.right_progress_bar.setVisible(False)
        self.right_progress_bar.setRange(0, 0)
        self.right_progress_bar.setFixedHeight(3)
        self.right_progress_bar.setTextVisible(False)
        
        self.right_pane_widget = QWidget()
        self.right_pane_widget.setObjectName("rightPane")
        self.right_pane_layout = QVBoxLayout(self.right_pane_widget)
        self.right_pane_layout.setContentsMargins(0, 0, 0, 0)
        self.right_pane_layout.setSpacing(0)
        
        self.right_pane_layout.addWidget(self.right_progress_bar)
        self.right_pane_layout.addWidget(self.list_view, 1)

        self.list_view.setMouseTracking(True)
        self.list_view.entered.connect(self.on_list_view_entered)

        self.bento_grid = QWidget()
        self.bento_grid.setObjectName("bentoGrid")
        bento_layout = QGridLayout(self.bento_grid)
        bento_layout.setContentsMargins(8, 8, 8, 8)
        bento_layout.setHorizontalSpacing(8)
        bento_layout.setVerticalSpacing(8)

        self.thumbnail_preview = VideoThumbnailPreview(
            self.right_pane_widget,
            max_thumbnails=self.video_thumbnail_count,
            thumbnail_size=self.video_thumbnail_size,
            cache_size_mb=self.video_digest_cache_size_mb,
        )
        self.thumbnail_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bento_layout.addWidget(self.thumbnail_preview, 0, 0, 2, 2)

        self.recent_history_card = self._create_bento_info_card("最近の履歴", "履歴なし")
        self.recent_history_value = self.recent_history_card.findChild(QLabel, "bentoValue")
        bento_layout.addWidget(self.recent_history_card, 0, 2)

        self.storage_card = self._create_bento_info_card("ストレージ容量", "取得中")
        self.storage_value = self.storage_card.findChild(QLabel, "bentoValue")
        bento_layout.addWidget(self.storage_card, 1, 2)

        bento_layout.setColumnStretch(0, 2)
        bento_layout.setColumnStretch(1, 2)
        bento_layout.setColumnStretch(2, 1)

        self.right_pane_layout.addWidget(self.bento_grid, 0)
        self.right_pane_layout.setStretch(0, 0)
        self.right_pane_layout.setStretch(1, 1)
        self.right_pane_layout.setStretch(2, 0)

        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.right_pane_widget)

        self.splitter.setSizes([300, 900])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)

        handle = self.splitter.handle(1)
        handle.setEnabled(True)
        self._collapse_filter = _SplitterCollapseFilter(self.splitter)
        handle.installEventFilter(self._collapse_filter)
        self.splitter.splitterMoved.connect(lambda *_: self._save_splitter_state())

    def _create_bento_info_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("bentoCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("bentoTitle")
        value_label = QLabel(value)
        value_label.setObjectName("bentoValue")
        value_label.setWordWrap(True)

        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        card_layout.addStretch()
        return card

    @staticmethod
    def _format_capacity(value: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        amount = float(value)
        unit = units[0]
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                break
            amount /= 1024
        return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"

    def _update_bento_cards(self) -> None:
        if hasattr(self, "recent_history_value") and self.recent_history_value is not None:
            recent = [
                os.path.basename(path.rstrip("\\/")) or path
                for path in reversed(getattr(self, "_nav_history", [])[-3:])
                if path
            ]
            self.recent_history_value.setText(" / ".join(recent) if recent else "履歴なし")

        if hasattr(self, "storage_value") and self.storage_value is not None:
            try:
                usage = shutil.disk_usage(self.current_path)
                free = self._format_capacity(usage.free)
                total = self._format_capacity(usage.total)
                percent = int((usage.used / usage.total) * 100) if usage.total else 0
                self.storage_value.setText(f"{free} 空き / {total}  ({percent}% 使用)")
            except Exception as e:
                logger.debug(f"Failed to get disk usage: {e}")
                self.storage_value.setText("容量を取得できません")
    
    def show_right_progress(self, message="読み込み中..."):
        self.right_progress_bar.setVisible(True)
        self.right_progress_bar.setFormat(message)
        self.list_view.setEnabled(False)
    
    def hide_right_progress(self):
        self.right_progress_bar.setVisible(False)
        self.list_view.setEnabled(True)
    
    def create_toolbar(self):
        self.toolbar = QToolBar("ツールバー")
        self.toolbar.setObjectName("mainToolBar")
        self.toolbar.setMovable(True)
        self.toolbar.setFloatable(True)
        self.toolbar.setWindowTitle("ツールバー")
        self._create_toolbar_widgets()
        self._rebuild_toolbar_items()

    def _create_toolbar_widgets(self):
        try:
            from .ui_icons import apply_icon_to_button as _apply_icon
        except ImportError:
            def _apply_icon(btn, name, fallback, **kw):
                btn.setText(fallback)

        self.up_button = QPushButton()
        self.up_button.setToolTip("上へ")
        _apply_icon(self.up_button, "up", "↑")
        self.up_button.clicked.connect(self.navigate_up)

        self.refresh_button = QPushButton()
        self.refresh_button.setToolTip("更新")
        _apply_icon(self.refresh_button, "refresh", "↻")
        self.refresh_button.clicked.connect(self.refresh)

        self.copy_button = QPushButton()
        self.copy_button.setToolTip("コピー")
        _apply_icon(self.copy_button, "copy", "📋")
        self.copy_button.clicked.connect(self.copy_selected_files)
        self.copy_button.setEnabled(False)

        self.cut_button = QPushButton()
        self.cut_button.setToolTip("切り取り")
        _apply_icon(self.cut_button, "cut", "✂")
        self.cut_button.clicked.connect(self.cut_selected_files)
        self.cut_button.setEnabled(False)

        self.paste_button = QPushButton()
        self.paste_button.setToolTip("貼り付け")
        _apply_icon(self.paste_button, "paste", "📌")
        self.paste_button.clicked.connect(self.paste_files)
        self.paste_button.setEnabled(False)

        self.delete_button = QPushButton()
        self.delete_button.setToolTip("ゴミ箱へ移動")
        _apply_icon(self.delete_button, "delete", "🗑")
        self.delete_button.clicked.connect(self.move_selected_files_to_trash)
        self.delete_button.setEnabled(False)

        self.rename_button = QPushButton()
        self.rename_button.setToolTip("名前変更")
        _apply_icon(self.rename_button, "rename", "✏")
        self.rename_button.clicked.connect(self.rename_selected_file)

        self.new_folder_button = QPushButton()
        self.new_folder_button.setToolTip("新規フォルダ")
        _apply_icon(self.new_folder_button, "new_folder", "📁")
        self.new_folder_button.clicked.connect(self.create_new_folder)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["リスト表示", "アイコン表示", "詳細表示"])
        self.view_mode_combo.currentTextChanged.connect(self.change_view_mode)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["名前", "サイズ", "更新日", "種類"])
        self.sort_combo.currentTextChanged.connect(self.change_sort_order)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("ファイル名で検索...")
        self.search_box.setMinimumWidth(160)

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(150)
        self._search_debounce_timer.timeout.connect(
            lambda: self.filter_files(self.search_box.text())
        )
        self.search_box.textChanged.connect(
            lambda _: self._search_debounce_timer.start()
        )

        self.foreign_filename_checkbox = QCheckBox("外国語名")
        self.foreign_filename_checkbox.setToolTip("外国語と思われるファイル名のみ表示")
        self.foreign_filename_checkbox.toggled.connect(self.toggle_foreign_filename_filter)

        self.search_button = QPushButton()
        self.search_button.setToolTip("ファイル検索")
        _apply_icon(self.search_button, "search", "🔍")
        self.search_button.clicked.connect(self.show_file_search_dialog)

        self.hidden_button = QPushButton()
        self.hidden_button.setToolTip("隠しファイル表示切替")
        self.hidden_button.setCheckable(True)
        _apply_icon(self.hidden_button, "hidden", "👁")
        self.hidden_button.clicked.connect(self.toggle_hidden_files)

        self.disk_analysis_button = QPushButton()
        self.disk_analysis_button.setToolTip("ディスク使用量分析")
        _apply_icon(self.disk_analysis_button, "disk_analysis", "📊")
        self.disk_analysis_button.clicked.connect(self.show_disk_analysis_dialog)

        self.duplicate_videos_button = QPushButton()
        self.duplicate_videos_button.setToolTip("重複動画を検出")
        _apply_icon(self.duplicate_videos_button, "dup_videos", "🎬")
        self.duplicate_videos_button.clicked.connect(self.show_duplicate_videos_dialog)
        self.duplicate_videos_button.setEnabled(VIDEO_DUPLICATES_AVAILABLE)

        self.filename_similarity_button = QPushButton()
        self.filename_similarity_button.setToolTip("類似ファイル名を検出")
        _apply_icon(self.filename_similarity_button, "similar_files", "📄")
        self.filename_similarity_button.clicked.connect(self.show_filename_similarity_dialog)
        self.filename_similarity_button.setEnabled(FILENAME_SIMILARITY_AVAILABLE)

        self.same_filesize_button = QPushButton()
        self.same_filesize_button.setToolTip("同じファイルサイズのファイルを検出")
        _apply_icon(self.same_filesize_button, "same_size", "⚖")
        self.same_filesize_button.clicked.connect(self.show_same_filesize_dialog)
        self.same_filesize_button.setEnabled(SAME_FILESIZE_AVAILABLE)

        self.move_to_trash_button = QPushButton()
        self.move_to_trash_button.setToolTip("選択したファイルをゴミ箱に移動")
        _apply_icon(self.move_to_trash_button, "trash", "🗑️")
        self.move_to_trash_button.clicked.connect(self.move_selected_files_to_trash)
        self.move_to_trash_button.setEnabled(False)

        self.video_player_button = QPushButton()
        self.video_player_button.setToolTip("選択した動画を別ウィンドウで再生")
        _apply_icon(self.video_player_button, "video_player", "▶")
        self.video_player_button.clicked.connect(self.open_selected_video_player)
        self.video_player_button.setEnabled(VIDEO_PLAYER_AVAILABLE)

        self.settings_button = QPushButton()
        self.settings_button.setToolTip("設定")
        _apply_icon(self.settings_button, "settings", "⚙")
        self.settings_button.clicked.connect(self.show_settings)

    def _get_toolbar_widget(self, item_id: str):
        return {
            "up":           self.up_button,
            "refresh":      self.refresh_button,
            "copy":         self.copy_button,
            "cut":          self.cut_button,
            "paste":        self.paste_button,
            "delete":       self.delete_button,
            "rename":       self.rename_button,
            "new_folder":   self.new_folder_button,
            "view_mode":    self.view_mode_combo,
            "sort":         self.sort_combo,
            "search_box":   self.search_box,
            "foreign_filter": self.foreign_filename_checkbox,
            "search":       self.search_button,
            "hidden":       self.hidden_button,
            "disk_analysis":self.disk_analysis_button,
            "dup_videos":   self.duplicate_videos_button,
            "similar_files":self.filename_similarity_button,
            "same_size":    self.same_filesize_button,
            "trash":        self.move_to_trash_button,
            "video_player":  self.video_player_button,
            "settings":     self.settings_button,
        }.get(item_id)

    _ICON_REFRESH_MAP = [
        ("up_button",               "up",           "↑"),
        ("refresh_button",          "refresh",      "↻"),
        ("copy_button",             "copy",         "📋"),
        ("cut_button",              "cut",          "✂"),
        ("paste_button",            "paste",        "📌"),
        ("delete_button",           "delete",       "🗑"),
        ("rename_button",           "rename",       "✏"),
        ("new_folder_button",       "new_folder",   "📁"),
        ("search_button",           "search",       "🔍"),
        ("hidden_button",           "hidden",       "👁"),
        ("disk_analysis_button",    "disk_analysis","📊"),
        ("duplicate_videos_button", "dup_videos",   "🎬"),
        ("filename_similarity_button","similar_files","📄"),
        ("same_filesize_button",    "same_size",    "⚖"),
        ("move_to_trash_button",    "trash",        "🗑️"),
        ("video_player_button",     "video_player", "▶"),
        ("settings_button",         "settings",     "⚙"),
        ("back_button",             "nav_back",     "‹"),
        ("forward_button",          "nav_forward",  "›"),
    ]

    def refresh_icons(self) -> None:
        try:
            from .ui_icons import apply_icon_to_button
        except ImportError:
            return
        for attr, icon_name, fallback in self._ICON_REFRESH_MAP:
            btn = getattr(self, attr, None)
            if btn is not None:
                apply_icon_to_button(btn, icon_name, fallback)

    def _rebuild_toolbar_items(self):
        for action in list(self.toolbar.actions()):
            widget = self.toolbar.widgetForAction(action)
            if widget is not None:
                widget.hide()
            self.toolbar.removeAction(action)
            action.deleteLater()
        try:
            self.settings.sync()
            order_str = normalize_toolbar_order(
                self.settings.value("toolbar_order", TOOLBAR_DEFAULT_ORDER)
            )
        except Exception:
            order_str = TOOLBAR_DEFAULT_ORDER
        has_widget = False
        for item_id in [x.strip() for x in order_str.split(",") if x.strip()]:
            if item_id == "SEP":
                self.toolbar.addSeparator()
            else:
                widget = self._get_toolbar_widget(item_id)
                if widget is not None:
                    self.toolbar.addWidget(widget)
                    # QToolBar.clear() で外したウィジェットは hidden フラグが残るため、
                    # 再追加後に明示的に表示し直さないとツールバーから消えてしまう。
                    widget.setVisible(True)
                    has_widget = True
        if not has_widget and order_str != TOOLBAR_DEFAULT_ORDER:
            self.settings.setValue("toolbar_order", TOOLBAR_DEFAULT_ORDER)
            self.settings.sync()
            self._rebuild_toolbar_items()
            return
        if has_widget:
            self.toolbar.show()

    def rebuild_toolbar(self):
        self._rebuild_toolbar_items()
    
    def setup_models(self):
        self.file_system_model = CustomFileSystemModel()
        self.file_system_model.setRootPath("")
        
        self.proxy_model = FileSortFilterProxyModel()
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.file_system_model)
        
        self.list_view.setModel(self.proxy_model)
        self.update_filter_only()
        self.set_current_path(self.current_path)
    
    def connect_signals(self):
        self.left_pane.tree_view.selectionModel().currentChanged.connect(self.on_tree_selection_changed)
        self.left_pane.tree_view.clicked.connect(self._on_tree_clicked)
        
        if hasattr(self.file_system_model, 'modelReset'):
            self.file_system_model.modelReset.connect(self._restore_current_root_index)

        self.list_view.doubleClicked.connect(self.on_list_double_clicked)
        self.list_view.selectionModel().selectionChanged.connect(self.on_list_selection_changed)
        self.list_view.middle_clicked.connect(self._on_list_middle_clicked)

        if hasattr(self.left_pane.tree_view, 'files_dropped'):
            self.left_pane.tree_view.files_dropped.connect(self.on_files_dropped_to_folder)

        if hasattr(self.file_system_model, 'metadata_fetch_requested'):
            self.file_system_model.metadata_fetch_requested.connect(self._request_metadata_fetch)

        # タグフィルタパネルとの接続
        if hasattr(self.left_pane, 'tag_filter') and self.left_pane.tag_filter is not None:
            self.left_pane.tag_filter.filter_changed.connect(self._on_tag_filter_changed)

    def setup_context_menus(self):
        self.left_pane.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.left_pane.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_list_context_menu)

    def _setup_shortcuts(self):
        if not hasattr(self, "right_pane_widget") or not hasattr(self, "list_view"):
            return
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.navigate_back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self.navigate_forward)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self.navigate_up)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_address_bar)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self.toggle_hidden_files)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, activated=self.create_new_folder)

        right_scope = self.right_pane_widget
        sc_trash = QShortcut(QKeySequence("Delete"), right_scope, activated=self.move_selected_files_to_trash)
        sc_trash.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_delete = QShortcut(QKeySequence("Shift+Delete"), right_scope, activated=self.delete_selected_files)
        sc_delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_rename = QShortcut(QKeySequence("F2"), right_scope, activated=self.rename_selected_file)
        sc_rename.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_select_all = QShortcut(QKeySequence(QKeySequence.StandardKey.SelectAll), right_scope, activated=self.select_all_files)
        sc_select_all.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_video = QShortcut(QKeySequence(Qt.Key.Key_Space), right_scope, activated=self.open_selected_video_player)
        sc_video.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.list_view, activated=self.navigate_up).setContext(Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.left_pane.tree_view, activated=self.navigate_up).setContext(Qt.ShortcutContext.WidgetShortcut)

        self._apply_shortcut_tooltips()

    def _apply_shortcut_tooltips(self):
        tip_map = {
            'up_button':            "上へ (Alt+↑)",
            'refresh_button':       "更新 (F5)",
            'rename_button':        "名前変更 (F2)",
            'delete_button':        "ゴミ箱へ移動 (Del)",
            'move_to_trash_button': "ゴミ箱へ移動 (Del)",
            'new_folder_button':    "新規フォルダ (Ctrl+Shift+N)",
            'hidden_button':        "隠しファイル表示切替 (Ctrl+H)",
            'video_player_button':   "選択した動画を別ウィンドウで再生 (Space)",
        }
        for attr, tip in tip_map.items():
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setToolTip(tip)

    def focus_address_bar(self):
        self._show_address_editor()
        self.address_bar.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.address_bar.selectAll()

    def eventFilter(self, watched, event):
        if watched is getattr(self, "address_bar", None):
            if event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._show_breadcrumb_bar)
        elif watched is getattr(self, "breadcrumb_bar", None):
            if event.type() == QEvent.Type.MouseButtonPress:
                self.focus_address_bar()
                return True
        return super().eventFilter(watched, event)

    def _show_address_editor(self) -> None:
        if hasattr(self, "address_stack"):
            self.address_stack.setCurrentWidget(self.address_bar)

    def _show_breadcrumb_bar(self, force: bool = False) -> None:
        if not hasattr(self, "address_stack"):
            return
        if self.address_bar.hasFocus() and not force:
            return
        self.address_bar.setText(self.current_path)
        self.address_stack.setCurrentWidget(self.breadcrumb_bar)

    def _clear_breadcrumb(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _breadcrumb_segments(path: str) -> list[tuple[str, str]]:
        normalized = os.path.normpath(path)
        drive, tail = os.path.splitdrive(normalized)
        segments: list[tuple[str, str]] = []

        if drive:
            root = drive + os.sep
            segments.append((root, root))
            current = root
            parts = [part for part in tail.strip("\\/").split(os.sep) if part]
        elif normalized.startswith(os.sep):
            segments.append((os.sep, os.sep))
            current = os.sep
            parts = [part for part in normalized.strip(os.sep).split(os.sep) if part]
        else:
            current = ""
            parts = [part for part in normalized.split(os.sep) if part]

        for part in parts:
            current = os.path.join(current, part) if current else part
            segments.append((part, current))
        return segments

    def _update_breadcrumb_bar(self, path: str) -> None:
        if not hasattr(self, "breadcrumb_layout"):
            return
        self._clear_breadcrumb()

        segments = self._breadcrumb_segments(path)
        if not segments:
            label = QLabel(path)
            label.setObjectName("breadcrumbCurrent")
            self.breadcrumb_layout.addWidget(label)
        else:
            for index, (label_text, target_path) in enumerate(segments):
                if index > 0:
                    separator = QLabel("›")
                    separator.setObjectName("breadcrumbSeparator")
                    separator.setCursor(Qt.CursorShape.IBeamCursor)
                    self.breadcrumb_layout.addWidget(separator)

                button = QPushButton(label_text)
                button.setObjectName("breadcrumbSegment")
                button.setToolTip(target_path)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(partial(self.set_current_path, target_path))
                self.breadcrumb_layout.addWidget(button)

        self.breadcrumb_layout.addStretch(1)
    
    def on_drive_selected(self, drive):
        drive_path = f"{drive}:\\" if sys.platform == "win32" else drive
        try:
            self.settings.setValue("last_drive", drive)
        except Exception as e:
            logger.debug(f"Failed to save last_drive: {e}")
        self.set_current_path(drive_path)

    def set_current_path(self, path):
        old = getattr(self, 'current_path', None)
        if not getattr(self, '_nav_jumping', False) and old and old != path:
            self._nav_history.append(old)
            self._nav_forward_stack.clear()
        self.current_path = path
        self.address_bar.setText(path)
        self._update_breadcrumb_bar(path)
        self._show_breadcrumb_bar()
        self._sync_left_pane_to_path(path)
        self._update_nav_buttons()
        self._update_bento_cards()
        try:
            self.settings.setValue("last_path", path)
        except Exception as e:
            logger.debug(f"Failed to save current path: {e}")
        self.set_current_path_async(path)
        self._refresh_tag_filter(path)

    def _refresh_tag_filter(self, path: str) -> None:
        """パス変更時にタグフィルタパネルを更新する。"""
        if not VIDEO_CLUSTER_AVAILABLE:
            return
        tf = getattr(self.left_pane, 'tag_filter', None)
        if tf is None:
            return
        db = self._get_cluster_db()
        if db is None:
            return
        tf.set_db(db)
        tf.refresh(path)

    def _get_cluster_db(self) -> "VideoClusterDB | None":
        if not VIDEO_CLUSTER_AVAILABLE or VideoClusterDB is None:
            return None
        if self._cluster_db is None:
            try:
                self._cluster_db = VideoClusterDB()
            except Exception as e:
                logger.warning(f"VideoClusterDB 初期化失敗: {e}")
                return None
        return self._cluster_db

    def _on_tag_filter_changed(self, tags: list) -> None:
        """タグフィルタ変更時にファイルリストのフィルタを更新する。"""
        self._active_tag_filter = list(tags)
        self._apply_tag_filter()

    def _apply_tag_filter(self) -> None:
        """アクティブなタグフィルタをプロキシモデルに反映する。"""
        if not hasattr(self, 'proxy_model'):
            return
        if not self._active_tag_filter:
            # フィルタ解除
            if hasattr(self.proxy_model, 'set_tag_filter'):
                self.proxy_model.set_tag_filter([], None)
            return
        db = self._get_cluster_db()
        if db is None:
            return
        matching = set(db.get_videos_with_tags(self._active_tag_filter, self.current_path))
        if hasattr(self.proxy_model, 'set_tag_filter'):
            self.proxy_model.set_tag_filter(self._active_tag_filter, matching)

    def _sync_left_pane_to_path(self, path):
        if self._syncing_left_pane or not path or not os.path.isdir(path):
            return
        # select_drive / expand / fetchMore が currentChanged を誘発しないよう
        # 操作全体をフラグで保護する
        self._syncing_left_pane = True
        try:
            root_changed = False
            if sys.platform == "win32":
                drive, _ = os.path.splitdrive(path)
                if drive:
                    root_path = os.path.abspath(drive + "\\")
                    current_root = getattr(self.left_pane, "_current_root_path", "")
                    root_changed = (
                        os.path.normcase(root_path) != os.path.normcase(current_root)
                    )
                    self.left_pane.select_drive(drive.rstrip(":"))
            elif path.startswith(os.sep):
                current_root = getattr(self.left_pane, "_current_root_path", "")
                root_changed = os.path.normcase(os.sep) != os.path.normcase(current_root)
                if root_changed:
                    self.left_pane.select_drive(os.sep)

            if root_changed:
                self._schedule_tree_sync(path)
                return

            self._trigger_tree_load_for_path(path)
            folder_model = self.left_pane.folder_model
            tree_index = folder_model.index(path)
            if tree_index.isValid():
                self._apply_tree_selection(tree_index, path)
            else:
                self._schedule_tree_sync(path)
        except Exception as e:
            logger.error(f"Error syncing left pane: {e}")
        finally:
            self._syncing_left_pane = False

    def _trigger_tree_load_for_path(self, path):
        folder_model = self.left_pane.folder_model
        tree_view = self.left_pane.tree_view
        ancestors: list[str] = []
        current = path
        while True:
            parent = os.path.dirname(current)
            if parent == current: break
            ancestors.append(parent)
            current = parent
        ancestors.reverse()
        for ancestor in ancestors:
            idx = folder_model.index(ancestor)
            if idx.isValid():
                tree_view.expand(idx)
                if folder_model.canFetchMore(idx):
                    folder_model.fetchMore(idx)

    def _apply_tree_selection(self, tree_index, path):
        tree_view = self.left_pane.tree_view
        # 呼び出し元がすでにフラグを立てている場合があるため save/restore する
        was_syncing = self._syncing_left_pane
        self._syncing_left_pane = True
        try:
            p_idx = tree_index.parent()
            while p_idx.isValid():
                tree_view.expand(p_idx)
                p_idx = p_idx.parent()
            tree_view.setCurrentIndex(tree_index)
            item_rect = tree_view.visualRect(tree_index)
            viewport_rect = tree_view.viewport().rect()
            if not item_rect.isValid() or not viewport_rect.contains(item_rect):
                tree_view.scrollTo(tree_index, QAbstractItemView.EnsureVisible)
        finally:
            self._syncing_left_pane = was_syncing
        try:
            self.settings.setValue("last_left_path", path)
        except Exception as e:
            logger.debug(f"Failed to save last_left_path: {e}")

    def _schedule_tree_sync(self, path, attempt=0):
        if attempt >= 8: return
        def retry():
            if getattr(self, 'current_path', None) != path: return
            if self._syncing_left_pane: return
            self._syncing_left_pane = True
            try:
                self._trigger_tree_load_for_path(path)
                tree_index = self.left_pane.folder_model.index(path)
                if tree_index.isValid(): self._apply_tree_selection(tree_index, path)
                else: self._schedule_tree_sync(path, attempt + 1)
            finally:
                self._syncing_left_pane = False
        QTimer.singleShot(150 * (attempt + 1), retry)

    def _update_nav_buttons(self):
        self.back_button.setEnabled(bool(self._nav_history))
        self.forward_button.setEnabled(bool(self._nav_forward_stack))

    def navigate_back(self):
        if not self._nav_history: return
        self._nav_forward_stack.append(self.current_path)
        target = self._nav_history.pop()
        self._nav_jumping = True
        try: self.set_current_path(target)
        finally: self._nav_jumping = False
        self._update_nav_buttons()

    def navigate_forward(self):
        if not self._nav_forward_stack: return
        self._nav_history.append(self.current_path)
        target = self._nav_forward_stack.pop()
        self._nav_jumping = True
        try: self.set_current_path(target)
        finally: self._nav_jumping = False
        self._update_nav_buttons()

    def navigate_to_address(self):
        path = self.address_bar.text().strip()
        if path and os.path.isdir(path):
            self.set_current_path(path)
            self._show_breadcrumb_bar(force=True)
        else:
            self.address_bar.setText(self.current_path)
            self._show_breadcrumb_bar(force=True)
    
    def set_current_path_async(self, path):
        self.show_right_progress(f"フォルダを読み込み中: {os.path.basename(path)}")
        QTimer.singleShot(100, lambda: self.load_path_sync(path))
    
    def load_path_sync(self, path):
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"フォルダが見つかりません: {path}")
            source_index = self.file_system_model.setRootPath(path)
            if not source_index.isValid():
                source_index = self.file_system_model.index(path)
            if source_index.isValid():
                proxy_index = self.proxy_model.mapFromSource(source_index)
                self.list_view.setRootIndex(proxy_index)
            self.hide_right_progress()
        except Exception as e:
            logger.error(f"Error loading path {path}: {e}")
            self.hide_right_progress()
            QMessageBox.warning(self, "エラー", f"フォルダの読み込みに失敗しました:\n{str(e)}")

    def _restore_current_root_index(self):
        if not self.list_view or not self.proxy_model: return
        current_path = getattr(self, 'current_path', '')
        if not current_path or not os.path.isdir(current_path): return
        try:
            source_index = self.file_system_model.index(current_path)
            if source_index.isValid():
                proxy_index = self.proxy_model.mapFromSource(source_index)
                if proxy_index.isValid(): self.list_view.setRootIndex(proxy_index)
        except Exception as e:
            logger.debug(f"Failed to restore root index: {e}")

    def _restore_path(self, path: str) -> None:
        if not path or not os.path.isdir(path): return
        self.current_path = path
        self._restore_current_root_index()
        try:
            tree_index = self.left_pane.folder_model.index(path)
            if tree_index.isValid(): self.left_pane.tree_view.setCurrentIndex(tree_index)
        except Exception as e:
            logger.debug(f"Failed to restore path in tree: {e}")

    def _ensure_column_width(self, column: int, key: str) -> None:
        header = self.list_view.header()
        try:
            cw = header.sectionSize(column)
        except Exception:
            cw = None
        if cw is None or cw <= 12:
            target = self.DEFAULT_COLUMN_WIDTHS.get(key, 140)
            try: header.resizeSection(column, target)
            except Exception as e: logger.debug(f"Operation failed: {e}")

    def _on_tree_clicked(self, index):
        if self._syncing_left_pane: return
        if index.isValid():
            path = self.left_pane.folder_model.filePath(index)
            if os.path.isdir(path):
                if path != self.current_path:
                    self.set_current_path(path)
                    self.clear_file_selection()
                else:
                    self._sync_left_pane_to_path(path)
                try: self.settings.setValue("last_left_path", path)
                except Exception as e: logger.debug(f"Operation failed: {e}")

    def on_tree_selection_changed(self, current, previous):
        if self._syncing_left_pane: return
        if current.isValid():
            path = self.left_pane.folder_model.filePath(current)
            if os.path.isdir(path):
                self.set_current_path(path)
                try: self.settings.setValue("last_left_path", path)
                except Exception as e: logger.debug(f"Operation failed: {e}")
                self.clear_file_selection()
    
    def on_list_double_clicked(self, index):
        if index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            path = self.file_system_model.filePath(source_index)
            if os.path.isdir(path):
                self.set_current_path(path)
                self.clear_file_selection()
            else:
                self.open_file(path)

    def _on_list_middle_clicked(self, index):
        if getattr(self, 'video_digest_trigger', 'none') != 'middle':
            return
        if not index.isValid():
            return
        source_index = self.proxy_model.mapToSource(index)
        path = self.file_system_model.filePath(source_index)
        if self._is_video_file(path):
            self.show_video_digest(path)

    def on_list_selection_changed(self, selected, deselected):
        self._update_selected_file_actions()
        self.selection_changed.emit()
        hover_enabled = getattr(self, 'video_hover_thumbnail_enabled', True)
        indexes = self.list_view.selectedIndexes()
        if not indexes:
            if self.thumbnail_preview and hover_enabled: self.thumbnail_preview.display_video(None)
            return
        index = indexes[0]
        source_index = self.proxy_model.mapToSource(index)
        path = self.file_system_model.filePath(source_index)
        is_video = self._is_video_file(path)
        if self.thumbnail_preview and hover_enabled:
            self.thumbnail_preview.display_video(path if is_video else None)
        if is_video and getattr(self, 'video_auto_show_digest', False):
            QTimer.singleShot(500, lambda: self.show_video_digest(path))

    def _get_selected_row_indexes(self):
        if not self.list_view or self.list_view.selectionModel() is None: return []
        return self.list_view.selectionModel().selectedRows(0)

    def _get_selected_paths(self, *, files_only=False):
        selected_paths = []
        seen_paths = set()
        for index in self._get_selected_row_indexes():
            source_index = self.proxy_model.mapToSource(index)
            path = self.file_system_model.filePath(source_index)
            if not path or path in seen_paths: continue
            if files_only and not os.path.isfile(path): continue
            seen_paths.add(path)
            selected_paths.append(path)
        return selected_paths

    def _update_selected_file_actions(self):
        selected_count = len(self._get_selected_paths())
        self.copy_button.setEnabled(selected_count > 0)
        self.cut_button.setEnabled(selected_count > 0)
        self.paste_button.setEnabled(bool(self._clipboard_paths))
        self.delete_button.setEnabled(selected_count > 0)
        self.move_to_trash_button.setEnabled(selected_count > 0)
        if hasattr(self, 'video_player_button'):
            self.video_player_button.setEnabled(
                VIDEO_PLAYER_AVAILABLE
                and getattr(self, 'video_player_enabled', True)
                and bool(self._get_selected_video_path())
            )

    def on_list_view_entered(self, index):
        if not index.isValid() or not getattr(self, 'video_hover_thumbnail_enabled', True): return
        source_index = self.proxy_model.mapToSource(index)
        path = self.file_system_model.filePath(source_index)
        if self._is_video_file(path) and self.thumbnail_preview:
             self.thumbnail_preview.display_video(path)
    
    def show_file_search_dialog(self):
        try:
            import importlib
            mod = importlib.import_module('.file_search_dialog', package='file_manager')
            DialogClass = getattr(mod, 'FileSearchDialog')
            DialogClass(self).exec()
        except Exception as e:
            logger.error(f"Error showing search dialog: {e}")
            QMessageBox.warning(self, "エラー", f"ファイル検索ダイアログの表示中にエラーが発生しました: {e}")
    
    def show_duplicate_videos_dialog(self, target_path=None):
        if not VideoDuplicatesDialog:
            QMessageBox.warning(self, "エラー", "重複動画検出機能を利用できません。")
            return
        if target_path is None or isinstance(target_path, bool): target_path = self.current_path
        if not target_path or not os.path.isdir(target_path): return
        try: VideoDuplicatesDialog(target_path, self).exec()
        except Exception as e:
            logger.error(f"Error showing duplicates dialog: {e}")
            QMessageBox.warning(self, "エラー", f"重複動画の表示中にエラーが発生しました: {e}")

    def show_filename_similarity_dialog(self, target_path=None):
        if not FilenameSimilarityDialog:
            QMessageBox.warning(self, "エラー", "ファイル名類似度検出機能を利用できません。")
            return
        if target_path is None or isinstance(target_path, bool): target_path = self.current_path
        if not target_path or not os.path.isdir(target_path): return
        try:
            FilenameSimilarityDialog(target_path, self).exec()
            self.list_view.clearSelection()
        except Exception as e:
            logger.error(f"Error showing similarity dialog: {e}")
            QMessageBox.warning(self, "エラー", f"ファイル名類似度検出中にエラーが発生しました: {e}")

    def show_same_filesize_dialog(self, target_path=None):
        if not SameFileSizeDialog:
            QMessageBox.warning(self, "エラー", "同じファイルサイズ検出機能を利用できません。")
            return
        if target_path is None or isinstance(target_path, bool): target_path = self.current_path
        if not target_path or not os.path.isdir(target_path): return
        try: SameFileSizeDialog(self, target_path).exec()
        except Exception as e:
            logger.error(f"Error showing same size dialog: {e}")
            QMessageBox.warning(self, "エラー", f"同じファイルサイズ検出中にエラーが発生しました: {e}")

    def show_disk_analysis_dialog(self):
        try:
            import importlib
            mod = importlib.import_module('.disk_analysis_dialog', package='file_manager')
            DialogClass = getattr(mod, 'DiskAnalysisDialog')
            DialogClass(self.current_path, self).exec()
        except Exception as e:
            logger.error(f"Error showing disk analysis dialog: {e}")
            QMessageBox.warning(self, "エラー", f"ディスク分析ダイアログの表示中にエラーが発生しました: {e}")

    # ------------------------------------------------------------------
    # 動画クラスタリング
    # ------------------------------------------------------------------
    def show_video_cluster_scan_dialog(self, folder: str = "") -> None:
        if not VIDEO_CLUSTER_AVAILABLE or VideoClusterScanDialog is None:
            QMessageBox.information(self, "未対応", "動画クラスタリング機能が利用できません。")
            return
        db = self._get_cluster_db()
        if db is None:
            QMessageBox.warning(self, "エラー", "クラスタリングDBの初期化に失敗しました。")
            return
        dlg = VideoClusterScanDialog(db, folder or self.current_path, self)
        dlg.exec()
        # スキャン後にタグフィルタを更新
        self._refresh_tag_filter(self.current_path)

    def show_video_cluster_browser(self) -> None:
        if not VIDEO_CLUSTER_AVAILABLE or VideoClusterBrowserDialog is None:
            QMessageBox.information(self, "未対応", "動画クラスタリング機能が利用できません。")
            return
        db = self._get_cluster_db()
        if db is None:
            QMessageBox.warning(self, "エラー", "クラスタリングDBの初期化に失敗しました。")
            return
        VideoClusterBrowserDialog(db, self).exec()

    def move_selected_files_to_trash(self):
        selected_paths = self._get_selected_paths()
        if not selected_paths: return
        moved_count, failed_files = 0, []
        for path in selected_paths:
            try:
                if self.move_to_trash(path): moved_count += 1
                else: failed_files.append(path)
            except Exception as e: failed_files.append(f"{path} ({e})")
        if moved_count > 0:
            self.clear_file_selection()
            self.refresh()
            if failed_files:
                silent_warning(self, "一部失敗", f"{moved_count}個移動。失敗:\n" + "\n".join(failed_files))
        else: silent_warning(self, "エラー", "アイテムの移動に失敗しました。")
    
    def move_to_trash(self, file_path):
        try:
            import send2trash
            # send2trash は \\?\ プレフィックスを付加するため、バックスラッシュに正規化する
            normalized = os.path.normpath(file_path)
            send2trash.send2trash(normalized)
            return True
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Trash error ({file_path}): {e}")
            return False
        # send2trash が無い場合は winshell にフォールバック（Windows）
        if sys.platform == "win32":
            try:
                import winshell
                winshell.delete_file(file_path, no_confirm=True, allow_undo=True)
                return True
            except ImportError:
                logger.error("send2trash および winshell が見つかりません")
            except Exception as e:
                logger.error(f"Trash error ({file_path}): {e}")
        else:
            logger.error("send2trash が見つかりません")
        return False
    
    def select_all_files(self):
        self.list_view.selectAll()
        self._update_selected_file_actions()
    
    def clear_file_selection(self):
        self.list_view.clearSelection()
        self._update_selected_file_actions()
    
    def open_file(self, file_path):
        try:
            if sys.platform == "win32": os.startfile(file_path)
            elif sys.platform == "darwin": os.system(f"open '{file_path}'")
            else: os.system(f"xdg-open '{file_path}'")
        except Exception as e:
            logger.error(f"Error opening file {file_path}: {e}")
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした: {e}")

    def _get_selected_video_path(self) -> str | None:
        for path in self._get_selected_paths(files_only=True):
            if self._is_video_file(path):
                return path
        return None

    def _ensure_video_player_window(self):
        if not VIDEO_PLAYER_AVAILABLE or VideoPlayerWindow is None:
            return None
        if self._video_player_window is None:
            self._video_player_window = VideoPlayerWindow(
                self,
                settings=self.settings,
                default_speed=getattr(self, 'video_player_default_speed', 1.0),
                default_muted=getattr(self, 'video_player_default_muted', True),
            )
        return self._video_player_window

    def open_selected_video_player(self):
        if not getattr(self, 'video_player_enabled', True):
            return
        path = self._get_selected_video_path()
        if not path:
            return
        player_window = self._ensure_video_player_window()
        if player_window is None:
            QMessageBox.warning(self, "エラー", "動画プレーヤー機能を利用できません。")
            return
        player_window.load_video(
            path,
            autoplay=getattr(self, 'video_player_autoplay', True),
        )

    def on_files_dropped_to_folder(self, source_paths, target_path):
        if not source_paths or not target_path: return
        operation = self._prompt_drop_operation(source_paths, target_path)
        if operation is None: return
        success_count, errors = self._transfer_paths_to_directory(
            source_paths,
            target_path,
            move=(operation == "move"),
            confirm_overwrite=True,
        )
        if success_count > 0:
            self.clear_file_selection()
            self.refresh()
        if errors:
            QMessageBox.warning(self, "エラー", f"{success_count}件処理、{len(errors)}件失敗:\n" + "\n".join(errors[:5]))

    def _prompt_drop_operation(self, source_paths, target_path):
        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Question)
        mb.setWindowTitle("ドロップ操作")
        mb.setText(f"{len(source_paths)} 件を {target_path} へコピーまたは移動します。")
        c_btn = mb.addButton("コピー", QMessageBox.AcceptRole)
        m_btn = mb.addButton("移動", QMessageBox.ActionRole)
        cancel_btn = mb.addButton("キャンセル", QMessageBox.RejectRole)
        mb.exec()
        clicked = mb.clickedButton()
        if clicked == c_btn: return "copy"
        if clicked == m_btn: return "move"
        return None

    def _transfer_paths_to_directory(self, source_paths, target_path, *, move=False, confirm_overwrite=False):
        success_count, errors = 0, []
        if not os.path.isdir(target_path): return 0, [f"保存先不明: {target_path}"]
        for sp in source_paths:
            try:
                dp = os.path.join(target_path, os.path.basename(sp))
                if os.path.abspath(sp) == os.path.abspath(dp): continue
                if os.path.exists(dp) and confirm_overwrite:
                    if not self._confirm_overwrite_destination(sp, dp):
                        break
                    self._remove_existing_path(dp)
                if os.path.exists(dp): errors.append(f"{dp}: 存在します"); continue
                if move: shutil.move(sp, dp)
                elif os.path.isdir(sp): shutil.copytree(sp, dp)
                else: shutil.copy2(sp, dp)
                success_count += 1
            except Exception as e: errors.append(f"{sp}: {e}")
        return success_count, errors

    def _confirm_overwrite_destination(self, source_path, destination_path):
        source_size = self._path_size(source_path)
        destination_size = self._path_size(destination_path)
        message = (
            "同名のファイルまたはフォルダが既に存在します。\n\n"
            f"移動/コピーする項目:\n{source_path}\n"
            f"サイズ: {self._format_byte_size(source_size)}\n\n"
            f"既存の項目:\n{destination_path}\n"
            f"サイズ: {self._format_byte_size(destination_size)}\n\n"
            "既存の項目を上書きしますか？"
        )
        reply = QMessageBox.question(
            self,
            "上書き確認",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _remove_existing_path(self, path):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _path_size(self, path):
        try:
            if os.path.isfile(path) or os.path.islink(path):
                return os.path.getsize(path)
            if os.path.isdir(path):
                total = 0
                for root, _, files in os.walk(path):
                    for name in files:
                        file_path = os.path.join(root, name)
                        try:
                            total += os.path.getsize(file_path)
                        except OSError:
                            pass
                return total
        except OSError:
            pass
        return None

    @staticmethod
    def _format_byte_size(size):
        if size is None:
            return "不明"
        value = float(max(0, size))
        units = ("B", "KB", "MB", "GB", "TB", "PB")
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024.0

    def show_tree_context_menu(self, position):
        index = self.left_pane.tree_view.indexAt(position)
        if not index.isValid(): return
        menu = self._build_tree_context_menu(index)
        menu.exec(self.left_pane.tree_view.mapToGlobal(position))

    def _build_tree_context_menu(self, index) -> QMenu:
        menu = QMenu(self)
        fp = self.left_pane.folder_model.filePath(index)
        menu.addAction("新規フォルダ", self.create_new_folder)
        menu.addAction("更新", self.refresh)
        menu.addSeparator()
        if VideoDuplicatesDialog and fp:
            action = menu.addAction("重複動画を検出")
            action.setData(fp)
            action.triggered.connect(self._show_tree_duplicate_action)
        if FilenameSimilarityDialog and fp:
            action = menu.addAction("類似ファイル名を検出")
            action.setData(fp)
            action.triggered.connect(self._show_tree_similarity_action)
        if DISK_ANALYSIS_AVAILABLE:
            menu.addAction("ディスク使用率分析", self.show_disk_analysis_dialog)
        if VIDEO_CLUSTER_AVAILABLE and fp:
            menu.addSeparator()
            menu.addAction("動画クラスタリング — フォルダをスキャン", partial(self.show_video_cluster_scan_dialog, fp))
            menu.addAction("動画クラスタリング — 結果を表示", self.show_video_cluster_browser)
        return menu

    def _show_tree_duplicate_action(self, _checked=False):
        action = self.sender()
        path = action.data() if isinstance(action, QAction) else None
        self.show_duplicate_videos_dialog(path)

    def _show_tree_similarity_action(self, _checked=False):
        action = self.sender()
        path = action.data() if isinstance(action, QAction) else None
        self.show_filename_similarity_dialog(path)

    def _build_list_context_menu(self, index) -> QMenu:
        menu = QMenu(self)
        menu.addAction("開く", self.open_selected_file)
        source_index = self.proxy_model.mapToSource(index)
        path = self.file_system_model.filePath(source_index)
        if self._is_video_file(path):
            player_action = menu.addAction("動画を別ウィンドウで再生", self.open_selected_video_player)
            player_action.setEnabled(
                VIDEO_PLAYER_AVAILABLE and getattr(self, 'video_player_enabled', True)
            )
            menu.addAction("動画ダイジェストを表示", partial(self.show_video_digest, path))
        menu.addSeparator()
        selected = bool(self._get_selected_paths())
        copy_action = menu.addAction("コピー", self.copy_selected_files)
        copy_action.setEnabled(selected)
        cut_action = menu.addAction("切り取り", self.cut_selected_files)
        cut_action.setEnabled(selected)
        paste_action = menu.addAction("貼り付け", self.paste_files)
        paste_action.setEnabled(bool(self._clipboard_paths))
        menu.addSeparator()
        menu.addAction("名前変更", self.rename_selected_file)
        t_act = menu.addAction("ファイル名を日本語に翻訳", self.translate_selected_filenames)
        t_act.setEnabled(TRANSLATION_FEATURE_AVAILABLE and bool(self._get_selected_file_paths()))
        attr_menu = menu.addMenu("属性を変更")
        attr_targets = bool(self._get_selected_paths(files_only=True))
        normal_attr = attr_menu.addAction("通常")
        normal_attr.triggered.connect(lambda: self.change_selected_file_attribute("normal"))
        readonly_attr = attr_menu.addAction("読み取り専用")
        readonly_attr.triggered.connect(lambda: self.change_selected_file_attribute("readonly"))
        hidden_attr = attr_menu.addAction("隠し")
        hidden_attr.triggered.connect(lambda: self.change_selected_file_attribute("hidden"))
        attr_menu.setEnabled(attr_targets)
        menu.addAction("削除", self.delete_selected_files)
        menu.addSeparator()
        menu.addAction("全て選択", self.select_all_files)
        menu.addAction("選択解除", self.clear_file_selection)
        trash_act = menu.addAction("選択したファイルをゴミ箱に移動", self.move_selected_files_to_trash)
        trash_act.setEnabled(bool(self._get_selected_paths(files_only=True)))
        return menu

    def show_list_context_menu(self, position):
        index = self.list_view.indexAt(position)
        if not index.isValid(): return
        selection = self.list_view.selectionModel()
        if selection is not None and not selection.isSelected(index):
            selection.select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            self.list_view.setCurrentIndex(index)
        self._build_list_context_menu(index).exec(self.list_view.mapToGlobal(position))

    def change_selected_file_attribute(self, attribute):
        paths = self._get_selected_paths(files_only=True)
        if not paths:
            return

        errors = []
        for path in paths:
            try:
                self._set_file_attribute(path, attribute)
            except Exception as e:
                errors.append(f"{path}: {e}")

        self.refresh()
        if errors:
            QMessageBox.warning(
                self,
                "属性変更エラー",
                f"{len(errors)} 件の属性変更に失敗しました。\n" + "\n".join(errors[:5]),
            )

    def _set_file_attribute(self, path, attribute):
        if attribute not in {"normal", "readonly", "hidden"}:
            raise ValueError(f"Unsupported attribute: {attribute}")
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        if sys.platform == "win32":
            self._set_windows_file_attribute(path, attribute)
            return

        self._set_posix_file_attribute(path, attribute)

    def _set_windows_file_attribute(self, path, attribute):
        import ctypes

        readonly = 0x01
        hidden = 0x02
        invalid = 0xFFFFFFFF
        kernel32 = ctypes.windll.kernel32
        attrs = kernel32.GetFileAttributesW(str(path))
        if attrs == invalid:
            raise OSError(f"属性を取得できません: {path}")

        if attribute == "normal":
            attrs &= ~readonly
            attrs &= ~hidden
        elif attribute == "readonly":
            attrs |= readonly
            attrs &= ~hidden
        elif attribute == "hidden":
            attrs |= hidden
            attrs &= ~readonly

        if not kernel32.SetFileAttributesW(str(path), attrs):
            raise OSError(f"属性を変更できません: {path}")

    def _set_posix_file_attribute(self, path, attribute):
        mode = os.stat(path).st_mode
        if attribute == "readonly":
            os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            self._rename_hidden_path(path, hidden=False)
        elif attribute == "hidden":
            os.chmod(path, mode | stat.S_IWUSR)
            self._rename_hidden_path(path, hidden=True)
        else:
            os.chmod(path, mode | stat.S_IWUSR)
            self._rename_hidden_path(path, hidden=False)

    def _rename_hidden_path(self, path, *, hidden):
        directory = os.path.dirname(path)
        name = os.path.basename(path)
        if not name:
            return path
        if hidden:
            if name.startswith("."):
                return path
            new_path = os.path.join(directory, f".{name}")
        else:
            if not name.startswith("."):
                return path
            new_name = name.lstrip(".")
            if not new_name:
                return path
            new_path = os.path.join(directory, new_name)
        if os.path.exists(new_path):
            raise FileExistsError(new_path)
        os.rename(path, new_path)
        return new_path
    
    def create_new_folder(self):
        name, ok = QInputDialog.getText(self, "新規フォルダ", "フォルダ名を入力してください:")
        if ok and name:
            try:
                os.makedirs(os.path.join(self.current_path, name), exist_ok=True)
                self.refresh()
            except Exception as e:
                logger.error(f"Failed to create folder: {e}")
                QMessageBox.warning(self, "エラー", f"フォルダを作成できませんでした: {e}")
    
    def refresh(self):
        try:
            old = self.current_path
            exp = self._capture_left_pane_expansion()
            self.file_system_model.beginResetModel()
            self.file_system_model.endResetModel()
            if hasattr(self.left_pane, 'folder_model'):
                self.left_pane.folder_model.beginResetModel()
                self.left_pane.folder_model.endResetModel()
            self.set_current_path_async(old)
            self._sync_left_pane_to_path(old)
            self._restore_left_pane_expansion(exp)
        except Exception as e:
            logger.error(f"Refresh error: {e}")
            self.set_current_path_async(self.current_path)

    def _capture_left_pane_expansion(self):
        paths = []
        tv, fm = self.left_pane.tree_view, self.left_pane.folder_model
        def _walk(p_idx):
            try: rows = fm.rowCount(p_idx)
            except Exception: return
            for r in range(rows):
                idx = fm.index(r, 0, p_idx)
                if idx.isValid() and tv.isExpanded(idx):
                    paths.append(fm.filePath(idx))
                    _walk(idx)
        try: _walk(tv.rootIndex())
        except Exception as e: logger.debug(f"Operation failed: {e}")
        return paths

    def _restore_left_pane_expansion(self, paths, attempt=0):
        if not paths or attempt >= 8: return
        tv, fm = self.left_pane.tree_view, self.left_pane.folder_model
        pending = []
        for p in sorted(paths, key=lambda x: x.count(os.sep)):
            idx = fm.index(p)
            if idx.isValid():
                tv.expand(idx)
                if fm.canFetchMore(idx): fm.fetchMore(idx)
            else: pending.append(p)
        if pending: QTimer.singleShot(150 * (attempt + 1), lambda: self._restore_left_pane_expansion(pending, attempt + 1))
    
    def open_selected_file(self):
        idxs = self.list_view.selectedIndexes()
        if idxs:
            path = self.file_system_model.filePath(self.proxy_model.mapToSource(idxs[0]))
            self.open_file(path)
    
    def copy_selected_files(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        self._clipboard_paths = paths
        self._clipboard_move = False
        self._update_selected_file_actions()

    def cut_selected_files(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        self._clipboard_paths = paths
        self._clipboard_move = True
        self._update_selected_file_actions()

    def paste_files(self):
        if not self._clipboard_paths:
            return
        target_path = self.current_path
        if not target_path or not os.path.isdir(target_path):
            silent_warning(self, "エラー", "貼り付け先フォルダが見つかりません。")
            return

        copied_paths = list(self._clipboard_paths)
        moved = self._clipboard_move
        success_count, errors = self._transfer_paths_to_directory(
            copied_paths,
            target_path,
            move=moved,
        )
        if success_count > 0:
            if moved:
                self._clipboard_paths = []
                self._clipboard_move = False
            self.clear_file_selection()
            self.refresh()
        if errors:
            message = f"{success_count}件処理、{len(errors)}件失敗:\n"
            silent_warning(self, "エラー", message + "\n".join(errors[:5]))
        self._update_selected_file_actions()

    def rename_selected_file(self):
        idxs = self.list_view.selectedIndexes()
        if not idxs: return
        source_idx = self.proxy_model.mapToSource(idxs[0])
        curr = self.file_system_model.fileName(source_idx)
        name, ok = QInputDialog.getText(self, "名前変更", "新しい名前を入力してください:", text=curr)
        if ok and name and name != curr:
            try:
                old = self.file_system_model.filePath(source_idx)
                os.rename(old, os.path.join(os.path.dirname(old), name))
                self.refresh()
            except Exception as e:
                logger.error(f"Rename error: {e}")
                QMessageBox.warning(self, "エラー", f"名前を変更できませんでした: {e}")

    def _get_selected_file_paths(self):
        return [Path(p) for p in self._get_selected_paths(files_only=True)]

    def translate_selected_filenames(self):
        if not TRANSLATION_FEATURE_AVAILABLE or not FilenameTranslationService: return
        paths = self._get_selected_file_paths()
        if not paths: return
        ts = FilenameTranslationService.from_env()
        if ts.requires_api_key and not ts.api_key:
            silent_information(self, "翻訳", f"APIキー未設定: {TRANSLATION_API_ENV_KEY}")
            return
        dialog = TranslatePreviewDialog(self, ts, paths)
        if dialog.exec() != QDialog.Accepted: return
        cands = dialog.get_selected_candidates()
        if not cands: return
        sum = RenameSummary()
        for c in cands:
            if not getattr(c, "is_ready", False): sum.skipped_count += 1; continue
            try:
                target = c.source_path.with_name(c.translated_name)
                _rename_file_without_overwrite(c.source_path, target)
                sum.renamed_count += 1
            except Exception as e: sum.error_messages.append(f"{c.original_name}: {e}")
        self.refresh()
        if sum.error_messages:
            silent_warning(self, "リネーム結果", f"成功: {sum.renamed_count}, 失敗: {len(sum.error_messages)}\n" + "\n".join(sum.error_messages[:5]))
    
    def delete_selected_files(self):
        paths = self._get_selected_paths()
        if not paths: return
        if silent_question(self, "削除確認", f"{len(paths)}個のアイテムを削除しますか？\n戻せません。", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                for p in paths:
                    if os.path.isdir(p): shutil.rmtree(p)
                    else: os.remove(p)
                self.clear_file_selection()
                self.refresh()
            except Exception as e:
                logger.error(f"Delete error: {e}")
                silent_warning(self, "エラー", f"削除できませんでした: {e}")
    
    def navigate_up(self):
        p = os.path.dirname(self.current_path)
        if p and p != self.current_path: self.set_current_path(p)
    
    def change_view_mode(self, mode):
        try:
            if mode == "リスト表示": self.view_mode = "list"
            elif mode == "アイコン表示": self.view_mode = "icon"
            else: self.view_mode = "detail"

            self.list_view.setHeaderHidden(self.view_mode != "detail")
            if self.view_mode == "detail": self.setup_detail_view()
            self.settings.setValue("view_mode", self.view_mode)
        except Exception as e:
            logger.error(f"View mode change error: {e}")
    
    def change_sort_order(self, sort_type):
        m = {"名前": 0, "サイズ": 1, "更新日": 3, "種類": 2}
        if sort_type in m:
            self.proxy_model.sort(m[sort_type], Qt.AscendingOrder if sort_type != "更新日" else Qt.DescendingOrder)
    
    def filter_files(self, text):
        # set_filename_filter_text 内で invalidateFilter() が呼ばれるため追加のリロードは不要
        self.proxy_model.set_filename_filter_text(text)

    def toggle_foreign_filename_filter(self, checked):
        # set_foreign_filename_only 内で invalidateFilter() が呼ばれるため追加のリロードは不要
        # (フォルダの再読み込みは非同期のため、直後にフィルタ結果が上書きされる原因になる)
        self.filter_foreign_filenames = bool(checked)
        self.proxy_model.set_foreign_filename_only(checked)

    def toggle_hidden_files(self):
        self.show_hidden = not self.show_hidden
        self.hidden_button.setChecked(self.show_hidden)
        self.settings.setValue("show_hidden", self.show_hidden)
        self.update_filter_only()
        self.refresh()

    def update_filter_only(self):
        f = QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot
        if self.show_hidden:
            f |= QDir.Hidden | QDir.System
        self.file_system_model.setFilter(f)
        if hasattr(self.left_pane, 'folder_model'):
            folder_filter = QDir.AllDirs | QDir.NoDotAndDotDot
            if self.show_hidden:
                folder_filter |= QDir.Hidden | QDir.System
            self.left_pane.folder_model.setFilter(folder_filter)

    def setup_custom_delegate(self):
        self.file_delegate = FileItemDelegate(self)
        self.list_view.setItemDelegate(self.file_delegate)
        if hasattr(self.left_pane, 'tree_view'):
            self.left_pane.tree_view.setItemDelegate(FileItemDelegate(self))
    
    def setup_detail_view(self):
        h = self.list_view.header()
        h.setStretchLastSection(False)
        for i in range(h.count()): h.setSectionResizeMode(i, QHeaderView.Interactive)
        for k, c in self.DETAIL_VIEW_COLUMNS: h.resizeSection(c, self.DEFAULT_COLUMN_WIDTHS.get(k, 100))
        self.restore_column_widths()
        self._restore_list_header_state()
        self.update_column_visibility()
        h.sectionResized.connect(self.save_column_widths)
        h.sectionMoved.connect(lambda *_: self._save_list_header_state())
        h.sortIndicatorChanged.connect(lambda *_: self._save_list_header_state())

    def save_column_widths(self):
        h = self.list_view.header()
        self.settings.setValue(self.COLUMN_WIDTHS_KEY, [h.sectionSize(i) for i in range(h.count())])

    def _save_list_header_state(self):
        try: self.settings.setValue("list_header_state", self.list_view.header().saveState())
        except Exception as e: logger.debug(f"Header state save error: {e}")

    def _restore_list_header_state(self):
        try:
            s = self.settings.value("list_header_state")
            if s: self.list_view.header().restoreState(s)
        except Exception as e: logger.debug(f"Header state restore error: {e}")

    def _save_splitter_state(self):
        try: self.settings.setValue("splitter_sizes", [int(s) for s in self.splitter.sizes()])
        except Exception as e: logger.debug(f"Splitter state save error: {e}")

    def _restore_splitter_state(self):
        try:
            r = self.settings.value("splitter_sizes")
            if r:
                sizes = [int(v) for v in r]
                if len(sizes) >= 2:
                    total = max(sum(sizes), 900)
                    left = max(sizes[0], 200)
                    right = max(total - left, 400)
                    self.splitter.setSizes([left, right])
        except Exception as e: logger.debug(f"Splitter state restore error: {e}")

    def save_window_state(self):
        self._save_splitter_state()
        self._save_list_header_state()
        self.save_column_widths()
        self.save_settings()
        self.settings.sync()

    def restore_column_widths(self):
        h = self.list_view.header()
        ws = self.settings.value(self.COLUMN_WIDTHS_KEY)
        if isinstance(ws, list) and len(ws) == h.count():
            for i, w in enumerate(ws):
                try: h.resizeSection(i, int(w))
                except Exception: continue
        for k, c in self.DETAIL_VIEW_COLUMNS:
            if self.visible_columns.get(k, False) or k == 'name': self._ensure_column_width(c, k)

    def update_column_visibility(self):
        v = self.list_view
        for k, c in self.DETAIL_VIEW_COLUMNS:
            show = self.visible_columns.get(k, k == 'name')
            try:
                v.setColumnHidden(c, not show)
                if show: self._ensure_column_width(c, k)
            except Exception: continue
        v.viewport().update()

    def show_settings(self):
        try:
            self.settings.sync()
            self.load_settings()
            old_p, old_cols = self.current_path, self.visible_columns.copy()
            if SettingsDialog(self, self.settings, old_cols).exec() == QDialog.Accepted:
                self.settings.sync()
                self.load_settings()
                self.file_system_model.update_visible_columns(self.visible_columns)
                self.update_column_visibility()
                self.restore_column_widths()
                self.rebuild_toolbar()
                if old_p and os.path.isdir(old_p): self._restore_path(old_p)
        except Exception as e:
            logger.error(f"Settings apply error: {e}")

    def show_video_digest(self, video_path):
        if not VIDEO_DIGEST_AVAILABLE: return
        try: VideoDigestDialog(video_path, self).exec()
        except Exception as e:
            logger.error(f"Video digest error: {e}")
            QMessageBox.warning(self, "エラー", f"動画ダイジェストの表示中にエラーが発生しました: {e}")

    @staticmethod
    def _create_settings():
        from PySide6 import QtCore  # 遅延インポートでテストを容易にする
        return QtCore.QSettings("FileManager", "Settings")

    def load_settings(self):
        s = self.settings

        # 表示列 — 失敗しても他グループに影響しない
        try:
            self.visible_columns = {
                "name": True,
                "size": coerce_bool(s.value("show_size", True), True),
                "type": coerce_bool(s.value("show_type", True), True),
                "modified": coerce_bool(s.value("show_modified", True), True),
                "permissions": coerce_bool(s.value("show_permissions", False), False),
                "created": coerce_bool(s.value("show_created", False), False),
                "attributes": coerce_bool(s.value("show_attributes", True), True),
                "extension": coerce_bool(s.value("show_extension", False), False),
                "owner": coerce_bool(s.value("show_owner", False), False),
                "group": coerce_bool(s.value("show_group", False), False),
                "duration": coerce_bool(s.value("show_duration", True), True),
                "resolution": coerce_bool(s.value("show_resolution", True), True),
                "fps": coerce_bool(s.value("show_fps", False), False),
            }
        except Exception as e:
            logger.error(f"Load visible_columns error: {e}")
            self.visible_columns = {
                "name": True, "size": True, "type": True, "modified": True,
                "permissions": False, "created": False, "attributes": True,
                "extension": False, "owner": False, "group": False,
                "duration": True, "resolution": True, "fps": False,
            }

        try:
            self.show_hidden = coerce_bool(s.value("show_hidden", True), True)
        except Exception as e:
            logger.error(f"Load show_hidden error: {e}")
            self.show_hidden = False

        try:
            self.attribute_colors = {
                "hidden": coerce_color(s.value("color_hidden", "#808080"), "#808080"),
                "readonly": coerce_color(s.value("color_readonly", "#0000FF"), "#0000FF"),
                "system": coerce_color(s.value("color_system", "#FF0000"), "#FF0000"),
                "normal": coerce_color(s.value("color_normal", "#000000"), "#000000"),
            }
        except Exception as e:
            logger.error(f"Load attribute_colors error: {e}")
            self.attribute_colors = {
                "hidden": "#808080", "readonly": "#0000FF",
                "system": "#FF0000", "normal": "#000000",
            }

        try:
            self.video_thumbnail_count = coerce_int(s.value("video_thumbnail_count", 6), 6, minimum=1, maximum=12)
            self.video_digest_max_frames = coerce_int(s.value("video_digest_max_frames", 12), 12, minimum=1, maximum=60)
            tw = coerce_int(s.value("video_thumbnail_width", 160), 160, minimum=80, maximum=400)
            th = coerce_int(s.value("video_thumbnail_height", 90), 90, minimum=60, maximum=300)
            self.video_thumbnail_size = (tw, th)
            old_auto = coerce_bool(s.value("video_auto_show_digest", False), False)
            trigger_default = "left" if old_auto else "none"
            self.video_digest_trigger = str(s.value("video_digest_trigger", trigger_default))
            self.video_auto_show_digest = (self.video_digest_trigger == "left")
            self.video_hover_thumbnail_enabled = coerce_bool(s.value("video_hover_thumbnail_enabled", False), False)
            self.video_digest_cache_size_mb = coerce_int(s.value("video_digest_cache_size_mb", 200), 200, minimum=1, maximum=2048)
            self.video_digest_burst_count = coerce_int(s.value("video_digest_burst_count", 0), 0, minimum=0, maximum=3)
            self.video_player_enabled = coerce_bool(s.value("video_player_enabled", True), True)
            self.video_player_default_muted = coerce_bool(s.value("video_player_default_muted", True), True)
            self.video_player_autoplay = coerce_bool(s.value("video_player_autoplay", True), True)
            speed_value = s.value("video_player_default_speed", 1.0)
            try:
                self.video_player_default_speed = float(speed_value)
            except (TypeError, ValueError):
                self.video_player_default_speed = 1.0
            if self.video_player_default_speed not in (1.0, 1.5, 2.0):
                self.video_player_default_speed = 1.0
        except Exception as e:
            logger.error(f"Load video settings error: {e}")
            self.video_thumbnail_count = 6
            self.video_digest_max_frames = 12
            self.video_thumbnail_size = (160, 90)
            self.video_digest_trigger = "none"
            self.video_auto_show_digest = False
            self.video_hover_thumbnail_enabled = False
            self.video_digest_cache_size_mb = 200
            self.video_digest_burst_count = 0
            self.video_player_enabled = True
            self.video_player_default_speed = 1.0
            self.video_player_default_muted = True
            self.video_player_autoplay = True

        try:
            self.view_mode = coerce_str(s.value("view_mode", "list"), "list")
        except Exception as e:
            logger.error(f"Load view_mode error: {e}")
            self.view_mode = "list"

        # UI への反映
        try:
            if hasattr(self, 'hidden_button'):
                self.hidden_button.setChecked(self.show_hidden)
            if hasattr(self, 'file_system_model'):
                self.update_filter_only()
                self.file_system_model.update_visible_columns(self.visible_columns)
            if hasattr(self, 'list_view'):
                self.update_column_visibility()
        except Exception as e:
            logger.error(f"Apply column settings error: {e}")

        try:
            if self.thumbnail_preview:
                self.thumbnail_preview.set_preferences(
                    max_thumbnails=self.video_thumbnail_count,
                    thumbnail_size=self.video_thumbnail_size,
                    cache_size_mb=self.video_digest_cache_size_mb,
                )
            if hasattr(self, 'bento_grid'):
                self.bento_grid.setVisible(self.video_hover_thumbnail_enabled)
        except Exception as e:
            logger.error(f"Apply thumbnail settings error: {e}")

        self.apply_fonts()

    def save_settings(self):
        try:
            s = self.settings
            for k, v in self.visible_columns.items():
                s.setValue(f"show_{k}", v)
            s.setValue("view_mode", self.view_mode)
            s.setValue("show_hidden", self.show_hidden)
            for k, v in self.attribute_colors.items():
                s.setValue(f"color_{k}", v)
            s.setValue("video_digest_trigger", getattr(self, 'video_digest_trigger', 'none'))
            s.setValue("video_auto_show_digest", getattr(self, 'video_auto_show_digest', False))
            s.setValue("video_thumbnail_count", getattr(self, 'video_thumbnail_count', 6))
            s.setValue("video_digest_max_frames", getattr(self, 'video_digest_max_frames', 12))
            if hasattr(self, 'video_thumbnail_size'):
                s.setValue("video_thumbnail_width", self.video_thumbnail_size[0])
                s.setValue("video_thumbnail_height", self.video_thumbnail_size[1])
            s.setValue("video_hover_thumbnail_enabled", getattr(self, 'video_hover_thumbnail_enabled', True))
            s.setValue("video_digest_cache_size_mb", getattr(self, 'video_digest_cache_size_mb', 200))
            s.setValue("video_digest_burst_count", getattr(self, 'video_digest_burst_count', 0))
            s.setValue("video_player_enabled", getattr(self, 'video_player_enabled', True))
            s.setValue("video_player_default_speed", getattr(self, 'video_player_default_speed', 1.0))
            s.setValue("video_player_default_muted", getattr(self, 'video_player_default_muted', True))
            s.setValue("video_player_autoplay", getattr(self, 'video_player_autoplay', True))
            s.sync()
        except Exception as e:
            logger.error(f"Save settings error: {e}")

    def show_column_menu(self, position):
        menu = QMenu(self)
        cols = [("ファイル名", "name", 0, False), ("サイズ", "size", 1, True), ("種類", "type", 2, True), ("更新日時", "modified", 3, True), ("権限", "permissions", 4, True), ("作成日時", "created", 5, True), ("属性", "attributes", 6, True), ("拡張子", "extension", 7, True), ("所有者", "owner", 8, True), ("グループ", "group", 9, True), ("再生時間", "duration", 10, True), ("解像度", "resolution", 11, True), ("FPS", "fps", 12, True)]
        for name, key, idx, hideable in cols:
            a = QAction(name, self)
            a.setCheckable(True)
            a.setChecked(self.visible_columns.get(key, False))
            a.setEnabled(hideable)
            a.setData({"key": key, "column_index": idx})
            a.triggered.connect(lambda checked, act=a: self.toggle_column(act))
            menu.addAction(a)
        menu.exec(self.list_view.header().mapToGlobal(position))

    def toggle_column(self, action):
        key = action.data()["key"]
        self.visible_columns[key] = action.isChecked()
        self.settings.setValue(f"show_{key}", action.isChecked())
        if hasattr(self, 'file_system_model'): self.file_system_model.update_visible_columns(self.visible_columns)
        self.update_column_visibility()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = FileManagerWidget()
    w.show()
    sys.exit(app.exec())
