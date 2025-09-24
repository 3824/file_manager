#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイルマネージャーのメインウィジェット
"""

import os
import string
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTreeView, QListView, QHeaderView, QMessageBox,
    QFileDialog, QInputDialog, QMenu, QAbstractItemView,
    QToolBar, QComboBox, QLineEdit, QPushButton, QFileSystemModel,
    QDialog, QFormLayout, QSpinBox, QFontComboBox, QCheckBox,
    QGroupBox, QButtonGroup, QRadioButton, QTabWidget, QStyledItemDelegate,
    QColorDialog, QLabel, QScrollArea, QFrame, QProgressBar
)
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, Signal, QSortFilterProxyModel, QTimer,
    QSettings, QFileInfo, QAbstractItemModel
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QFont, QColor, QPalette

# 動画ダイジェスト関連のインポート
try:
    from video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
    from video_digest_dialog import VideoDigestDialog
    from duplicate_video_dialog import DuplicateVideoDialog
    VIDEO_DIGEST_AVAILABLE = True
except ImportError:
    VIDEO_DIGEST_AVAILABLE = False
    OPENCV_AVAILABLE = False

# ファイル検索関連のインポート
try:
    from file_search_dialog import FileSearchDialog
    FILE_SEARCH_AVAILABLE = True
except ImportError:
    FILE_SEARCH_AVAILABLE = False

# ディスク分析関連のインポート
try:
    from disk_analysis_dialog import DiskAnalysisDialog
    DISK_ANALYSIS_AVAILABLE = True
except ImportError:
    DISK_ANALYSIS_AVAILABLE = False


class CustomFileSystemModel(QFileSystemModel):
    """カスタムファイルシステムモデル（追加列対応・チェックボックス選択機能付き）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.visible_columns = {
            "name": True,
            "size": True,
            "type": True,
            "modified": True,
            "permissions": False,
            "created": False,
            "attributes": False,
            "extension": False,
            "owner": False,
            "group": False
        }
        self.selected_files = set()  # 選択されたファイルのパスを管理
    
    def columnCount(self, parent=QModelIndex()):
        """列数を返す"""
        return 10  # 名前、サイズ、種類、更新日時、権限、作成日時、属性、拡張子、所有者、グループ
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """ヘッダーデータを返す"""
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            headers = [
                "名前", "サイズ", "種類", "更新日時", "権限", 
                "作成日時", "属性", "拡張子", "所有者", "グループ"
            ]
            if 0 <= section < len(headers):
                return headers[section]
        return super().headerData(section, orientation, role)
    
    def data(self, index, role=Qt.DisplayRole):
        """データを返す"""
        if not index.isValid():
            return None
        
        file_info = self.fileInfo(index)
        column = index.column()
        
        # チェックボックス機能（名前列のみ）
        if column == 0 and role == Qt.CheckStateRole:
            file_path = file_info.absoluteFilePath()
            return Qt.Checked if file_path in self.selected_files else Qt.Unchecked
        
        # 標準列（0-3）は親クラスの実装を使用
        if column < 4:
            return super().data(index, role)
        
        # カスタム列の実装
        if role == Qt.DisplayRole:
            if column == 4:  # 権限
                return self.get_permissions(file_info)
            elif column == 5:  # 作成日時
                try:
                    # birthTime()が存在しない場合はcreated()を使用
                    if hasattr(file_info, 'birthTime'):
                        return file_info.birthTime().toString("yyyy/MM/dd hh:mm:ss")
                    elif hasattr(file_info, 'created'):
                        return file_info.created().toString("yyyy/MM/dd hh:mm:ss")
                    else:
                        return file_info.lastModified().toString("yyyy/MM/dd hh:mm:ss")
                except Exception:
                    return "不明"
            elif column == 6:  # 属性
                return self.get_attributes(file_info)
            elif column == 7:  # 拡張子
                return file_info.suffix()
            elif column == 8:  # 所有者
                return self.get_owner(file_info)
            elif column == 9:  # グループ
                return self.get_group(file_info)
        
        # 色分けのための背景色設定
        if role == Qt.BackgroundRole and column == 6:  # 属性列
            return self.get_attribute_color(file_info)
        
        return None
    
    def setData(self, index, value, role=Qt.EditRole):
        """データを設定"""
        if not index.isValid():
            return False
        
        file_info = self.fileInfo(index)
        column = index.column()
        
        # チェックボックス機能（名前列のみ）
        if column == 0 and role == Qt.CheckStateRole:
            file_path = file_info.absoluteFilePath()
            if value == Qt.Checked:
                self.selected_files.add(file_path)
            else:
                self.selected_files.discard(file_path)
            
            # 選択状態が変更されたことを通知
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        
        return super().setData(index, value, role)
    
    def flags(self, index):
        """アイテムのフラグを返す"""
        if not index.isValid():
            return Qt.NoItemFlags
        
        column = index.column()
        
        # 名前列にチェックボックス機能を追加
        if column == 0:
            return super().flags(index) | Qt.ItemIsUserCheckable
        
        return super().flags(index)
    
    def get_selected_files(self):
        """選択されたファイルのリストを取得"""
        return list(self.selected_files)
    
    def clear_selection(self):
        """選択をクリア"""
        self.selected_files.clear()
        # 全データの変更を通知
        if self.rowCount() > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.CheckStateRole]
            )
    
    def select_all_files(self):
        """全てのファイルを選択"""
        self.selected_files.clear()
        for row in range(self.rowCount()):
            index = self.index(row, 0)
            file_info = self.fileInfo(index)
            if not file_info.isDir():  # ファイルのみ選択
                self.selected_files.add(file_info.absoluteFilePath())
        
        # 全データの変更を通知
        if self.rowCount() > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.CheckStateRole]
            )
    
    def get_selected_count(self):
        """選択されたファイル数を取得"""
        return len(self.selected_files)
    
    def get_permissions(self, file_info):
        """権限文字列を取得"""
        try:
            permissions = file_info.permissions()
            perm_str = ""
            
            # 読み取り権限
            perm_str += "r" if permissions & QFileInfo.Permission.ReadUser else "-"
            perm_str += "w" if permissions & QFileInfo.Permission.WriteUser else "-"
            perm_str += "x" if permissions & QFileInfo.Permission.ExeUser else "-"
            
            # グループ権限
            perm_str += "r" if permissions & QFileInfo.Permission.ReadGroup else "-"
            perm_str += "w" if permissions & QFileInfo.Permission.WriteGroup else "-"
            perm_str += "x" if permissions & QFileInfo.Permission.ExeGroup else "-"
            
            # その他権限
            perm_str += "r" if permissions & QFileInfo.Permission.ReadOther else "-"
            perm_str += "w" if permissions & QFileInfo.Permission.WriteOther else "-"
            perm_str += "x" if permissions & QFileInfo.Permission.ExeOther else "-"
            
            return perm_str
        except:
            return "---------"
    
    def get_attributes(self, file_info):
        """属性文字列を取得"""
        attributes = []
        
        if file_info.isHidden():
            attributes.append("隠し")
        if not file_info.isWritable():
            attributes.append("読み取り専用")
        # isSystem()はPySide6では削除されているため、代替手段を使用
        if file_info.isSymLink():
            attributes.append("シンボリックリンク")
        
        return ", ".join(attributes) if attributes else "通常"
    
    def get_owner(self, file_info):
        """所有者を取得"""
        try:
            path = file_info.absoluteFilePath()
            if sys.platform != "win32":
                import os
                import pwd
                stat_info = os.stat(path, follow_symlinks=False)
                owner = pwd.getpwuid(stat_info.st_uid).pw_name
                return owner
            else:
                # Windows環境では簡易的に固定表記
                return "User"
        except Exception:
            return "Unknown"
    
    def get_group(self, file_info):
        """グループを取得"""
        try:
            path = file_info.absoluteFilePath()
            if sys.platform != "win32":
                import os
                import grp
                stat_info = os.stat(path, follow_symlinks=False)
                group = grp.getgrgid(stat_info.st_gid).gr_name
                return group
            else:
                # Windows環境では簡易的に固定表記
                return "Users"
        except Exception:
            return "Unknown"
    
    def get_attribute_color(self, file_info):
        """属性に基づく色を取得"""
        if file_info.isHidden():
            return QColor("#808080")  # グレー
        elif not file_info.isWritable():
            return QColor("#0000FF")  # 青
        elif file_info.isSymLink():
            return QColor("#FF0000")  # 赤（シンボリックリンク）
        else:
            return QColor("#000000")  # 黒（通常）
    
    def update_visible_columns(self, visible_columns):
        """表示列設定を更新"""
        self.visible_columns = visible_columns.copy()
        self.layoutChanged.emit()


class FileSortFilterProxyModel(QSortFilterProxyModel):
    """サイズ列を数値としてソートするためのプロキシモデル"""

    def lessThan(self, left, right):
        try:
            # サイズ列（1列目）は数値で比較
            if left.column() == 1 and right.column() == 1 and hasattr(self.sourceModel(), 'fileInfo'):
                source_model = self.sourceModel()
                left_info = source_model.fileInfo(left)
                right_info = source_model.fileInfo(right)

                left_size = left_info.size() if left_info.isFile() else 0
                right_size = right_info.size() if right_info.isFile() else 0

                return left_size < right_size
        except Exception:
            # 何かあれば既定の比較にフォールバック
            pass

        # それ以外の列は既定の比較を利用
        return super().lessThan(left, right)


class LeftPaneWidget(QWidget):
    """左ペインウィジェット（ドライブボタン + フォルダツリー）"""
    
    drive_selected = Signal(str)  # ドライブが選択された時のシグナル
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_drive = None
        self.drive_buttons = {}
        self.worker_thread = None
        self.worker = None
        self.init_ui()
        self.setup_folder_tree()
        self.setup_drive_buttons()
    
    def cleanup_worker(self):
        """ワーカースレッドのクリーンアップ"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            if not self.worker_thread.wait(3000):  # 3秒でタイムアウト
                self.worker_thread.terminate()
                self.worker_thread.wait(3000)
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        
        if self.worker_thread:
            self.worker_thread.deleteLater()
            self.worker_thread = None
    
    def closeEvent(self, event):
        """ウィジェットが閉じられる時のクリーンアップ"""
        self.cleanup_worker()
        if self._qt_available:
            super().closeEvent(event)
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # ドライブボタンエリア
        self.drive_frame = QFrame()
        self.drive_frame.setFrameStyle(QFrame.StyledPanel)
        drive_layout = QVBoxLayout(self.drive_frame)
        drive_layout.setContentsMargins(5, 5, 5, 5)
        
        # ドライブボタンのスクロールエリア
        self.drive_scroll = QScrollArea()
        self.drive_scroll.setWidgetResizable(True)
        self.drive_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.drive_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.drive_scroll.setMaximumHeight(120)
        
        # ドライブボタンコンテナ
        self.drive_container = QWidget()
        self.drive_buttons_layout = QHBoxLayout(self.drive_container)
        self.drive_buttons_layout.setContentsMargins(5, 5, 5, 5)
        
        self.drive_scroll.setWidget(self.drive_container)
        drive_layout.addWidget(QLabel("ドライブ:"))
        drive_layout.addWidget(self.drive_scroll)
        
        layout.addWidget(self.drive_frame)
        
        # フォルダツリーエリア
        self.tree_frame = QFrame()
        self.tree_frame.setFrameStyle(QFrame.StyledPanel)
        tree_layout = QVBoxLayout(self.tree_frame)
        tree_layout.setContentsMargins(5, 5, 5, 5)
        
        tree_layout.addWidget(QLabel("フォルダ:"))
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # 不定プログレスバー
        self.progress_bar.setFixedHeight(20)
        tree_layout.addWidget(self.progress_bar)
        
        # フォルダツリー
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setRootIsDecorated(True)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)
        self.tree_view.setSortingEnabled(False)
        self.tree_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree_view.setExpandsOnDoubleClick(True)
        
        tree_layout.addWidget(self.tree_view)
        layout.addWidget(self.tree_frame)
        
        # レイアウトの比率設定
        layout.setStretchFactor(self.drive_frame, 0)
        layout.setStretchFactor(self.tree_frame, 1)
    
    def setup_drive_buttons(self):
        """ドライブボタンの設定"""
        # 利用可能なドライブを取得
        available_drives = self.get_available_drives()
        
        for drive in available_drives:
            button = QPushButton(drive)
            button.setCheckable(True)
            button.setFixedSize(30, 25)  # サイズを小さく（40x30 → 30x25）
            button.setStyleSheet("font-size: 10px;")  # フォントサイズも小さく
            button.clicked.connect(lambda checked, d=drive: self.on_drive_selected(d))
            self.drive_buttons[drive] = button
            self.drive_buttons_layout.addWidget(button)
        
        # 最初のドライブを選択
        if available_drives:
            self.select_drive(available_drives[0])
    
    def get_available_drives(self):
        """利用可能なドライブを取得"""
        drives = []
        if sys.platform == "win32":
            # Windowsの場合
            import string
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    drives.append(letter)
        else:
            # Unix系の場合
            drives = ["/"]
            # マウントポイントを取得
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            mount_point = parts[1]
                            if mount_point.startswith('/') and mount_point != '/':
                                drives.append(mount_point)
            except:
                pass
        
        return drives
    
    def setup_folder_tree(self):
        """フォルダツリーの設定"""
        # フォルダのみのモデル
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath("")
        self.folder_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        
        self.tree_view.setModel(self.folder_model)
        
        # ヘッダー設定
        header = self.tree_view.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setMinimumSectionSize(100)
        header.setDefaultSectionSize(200)
        
        # 不要な列を非表示
        for i in range(1, self.folder_model.columnCount()):
            self.tree_view.hideColumn(i)
    
    def show_progress(self, message="読み込み中..."):
        """プログレスバーを表示"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat(message)
        self.tree_view.setEnabled(False)
        # ドライブボタンも無効化
        for button in self.drive_buttons.values():
            button.setEnabled(False)
    
    def hide_progress(self):
        """プログレスバーを非表示"""
        self.progress_bar.setVisible(False)
        self.tree_view.setEnabled(True)
        # ドライブボタンを再有効化
        for button in self.drive_buttons.values():
            button.setEnabled(True)
    
    def on_drive_selected(self, drive):
        """ドライブが選択された時の処理"""
        self.select_drive_async(drive)
    
    def select_drive_async(self, drive):
        """非同期でドライブを選択"""
        self.current_drive = drive  # ドライブを設定
        
        if sys.platform == "win32":
            drive_path = f"{drive}:\\"
        else:
            drive_path = drive
        
        # プログレスバーを表示
        self.show_progress(f"ドライブ {drive} を読み込み中...")
        
        # QTimerを使用して非同期風に処理
        QTimer.singleShot(100, lambda: self.load_drive_sync(drive_path))
    
    def load_drive_sync(self, drive_path):
        """同期でドライブを読み込み"""
        try:
            # ドライブの存在確認
            if not os.path.exists(drive_path):
                raise FileNotFoundError(f"ドライブが見つかりません: {drive_path}")
            
            # フォルダモデルが存在することを確認
            if not hasattr(self, 'folder_model'):
                self.hide_progress()
                return
            
            # フォルダツリーのルートを設定
            root_index = self.folder_model.index(drive_path)
            if root_index.isValid():
                self.tree_view.setRootIndex(root_index)
                self.tree_view.expand(root_index)
            
            self.hide_progress()
            self.drive_selected.emit(self.current_drive)
            
        except Exception as e:
            self.hide_progress()
            QMessageBox.warning(self, "エラー", f"ドライブの読み込みに失敗しました:\n{str(e)}")
    
    
    def select_drive(self, drive):
        """ドライブを選択"""
        # ボタンの状態を更新
        for btn_drive, button in self.drive_buttons.items():
            button.setChecked(btn_drive == drive)
        
        self.current_drive = drive
        
        # フォルダモデルが存在することを確認
        if not hasattr(self, 'folder_model'):
            return
        
        # フォルダツリーのルートを設定
        if sys.platform == "win32":
            drive_path = f"{drive}:\\"
        else:
            drive_path = drive
        
        if os.path.exists(drive_path):
            root_index = self.folder_model.index(drive_path)
            if root_index.isValid():
                self.tree_view.setRootIndex(root_index)
                self.tree_view.expand(root_index)
    
    def get_selected_path(self):
        """現在選択されているパスを取得"""
        if not hasattr(self, 'folder_model'):
            return None
        
        current_index = self.tree_view.currentIndex()
        if current_index.isValid():
            return self.folder_model.filePath(current_index)
        return None


class FileManagerWidget(QWidget):
    """ファイルマネージャーのメインウィジェット"""
    
    def __init__(self, parent=None):
        self._owns_app = False
        self._owned_qapplication = None
        self._qt_available = isinstance(QApplication, type)

        if self._qt_available:
            app_instance = QApplication.instance()
            if app_instance is None:
                # ヘッドレス環境ではオフスクリーンプラットフォームを使用
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

            # QApplicationを保持しておく（GC対策）
            self._owned_qapplication = app_instance

            super().__init__(parent)
        else:
            # テスト用モック環境ではQWidget初期化をスキップ
            pass

        if not self._owned_qapplication and self._qt_available:
            self._owned_qapplication = QApplication.instance()
        self.current_path = QDir.homePath()
        self.settings = self._create_settings()
        self.view_mode = "list"  # "list" or "detail"
        self.show_hidden = False  # 隠しファイル表示フラグ
        # 設定から表示列を読み込み（デフォルト値を統一）
        self.visible_columns = {
            "name": True,  # 名前列は常に表示
            "size": True,
            "type": True,
            "modified": True,
            "permissions": False,
            "created": False,
            "attributes": False,
            "extension": False,
            "owner": False,
            "group": False
        }
        # ファイル属性による色設定
        self.attribute_colors = {
            "hidden": "#808080",      # グレー
            "readonly": "#0000FF",    # 青
            "system": "#FF0000",      # 赤
            "normal": "#000000"       # 黒
        }
        self.worker_thread = None
        self.worker = None
        self.video_digest_generator = VideoDigestGenerator() if VIDEO_DIGEST_AVAILABLE else None
        # まず設定を読み込み
        self.load_settings()

        # 前回終了時のフォルダを復元
        try:
            last_path = self.settings.value("last_path", "", type=str)
            if last_path and os.path.isdir(last_path):
                self.current_path = last_path
        except Exception:
            pass
        
        if self._qt_available:
            # UIを初期化
            self.init_ui()
            self.setup_models()
            self.connect_signals()
            self.setup_context_menus()
            self.setup_custom_delegate()

            # 最後に設定を適用（UIが準備完了してから）
            self.apply_settings()

    @staticmethod
    def _create_settings():
        """QSettingsインスタンスを生成"""
        from PySide6 import QtCore  # 遅延インポートでテストを容易にする

        return QtCore.QSettings("FileManager", "Settings")

    @staticmethod
    def _coerce_bool(value, default):
        """設定値を真偽値に変換"""
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def _coerce_str(value, default):
        """設定値を文字列に変換"""
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    @classmethod
    def _coerce_color(cls, value, default):
        """色設定を#RRGGBB形式に変換"""
        candidate = cls._coerce_str(value, default).strip()
        if (
            len(candidate) == 7
            and candidate.startswith("#")
            and all(c in string.hexdigits for c in candidate[1:])
        ):
            return candidate.upper()
        return default

    def cleanup_worker(self):
        """ワーカースレッドのクリーンアップ"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            if not self.worker_thread.wait(3000):  # 3秒でタイムアウト
                self.worker_thread.terminate()
                self.worker_thread.wait(3000)
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        
        if self.worker_thread:
            self.worker_thread.deleteLater()
            self.worker_thread = None
    
    def closeEvent(self, event):
        """ウィジェットが閉じられる時のクリーンアップ"""
        self.cleanup_worker()
        # 左ペインのクリーンアップも実行
        if hasattr(self, 'left_pane'):
            self.left_pane.cleanup_worker()
        # 設定を保存し、最後のパスを記録
        try:
            self.settings.setValue("last_path", self.current_path)
            self.save_settings()
        except Exception:
            pass
        super().closeEvent(event)
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ツールバーの作成
        self.create_toolbar()
        layout.addWidget(self.toolbar)
        
        # スプリッターの作成
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        
        # 左ペイン: ドライブボタン + フォルダツリー
        self.left_pane = LeftPaneWidget()
        self.left_pane.drive_selected.connect(self.on_drive_selected)
        
        # 右ペイン: ファイル一覧（詳細表示対応）
        self.list_view = QTreeView()
        self.list_view.setRootIsDecorated(False)
        self.list_view.setAlternatingRowColors(True)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setSortingEnabled(True)
        self.list_view.setHeaderHidden(False)
        
        # ヘッダーの右クリックメニューを設定
        header = self.list_view.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_column_menu)
        
        # 右ペイン用プログレスバー
        self.right_progress_bar = QProgressBar()
        self.right_progress_bar.setVisible(False)
        self.right_progress_bar.setRange(0, 0)  # 不定プログレスバー
        self.right_progress_bar.setFixedHeight(20)
        
        # 右ペイン用のコンテナウィジェット
        self.right_pane_widget = QWidget()
        self.right_pane_layout = QVBoxLayout(self.right_pane_widget)
        self.right_pane_layout.setContentsMargins(0, 0, 0, 0)
        self.right_pane_layout.setSpacing(0)
        
        # プログレスバーを右ペインに追加
        self.right_pane_layout.addWidget(self.right_progress_bar)
        
        # リストビューを右ペインに追加
        self.right_pane_layout.addWidget(self.list_view)
        
        # スプリッターにウィジェットを追加
        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.right_pane_widget)

        # スプリッターの比率設定とリサイズ可能にする
        self.splitter.setSizes([300, 900])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)  # ペインの完全な折りたたみを無効化

        # スプリッターハンドルの設定
        handle = self.splitter.handle(1)
        handle.setEnabled(True)
    
    def show_right_progress(self, message="読み込み中..."):
        """右ペインのプログレスバーを表示"""
        self.right_progress_bar.setVisible(True)
        self.right_progress_bar.setFormat(message)
        self.list_view.setEnabled(False)
    
    def hide_right_progress(self):
        """右ペインのプログレスバーを非表示"""
        self.right_progress_bar.setVisible(False)
        self.list_view.setEnabled(True)
    
    def create_toolbar(self):
        """ツールバーの作成"""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        
        # 上へボタン
        self.up_button = QPushButton("↑")
        self.up_button.setToolTip("上へ")
        self.up_button.clicked.connect(self.navigate_up)
        self.toolbar.addWidget(self.up_button)
        
        # 更新ボタン
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setToolTip("更新")
        self.refresh_button.clicked.connect(self.refresh)
        self.toolbar.addWidget(self.refresh_button)
        
        self.toolbar.addSeparator()
        
        # 表示モード切替
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["リスト表示", "アイコン表示", "詳細表示"])
        self.view_mode_combo.currentTextChanged.connect(self.change_view_mode)
        self.toolbar.addWidget(self.view_mode_combo)
        
        self.toolbar.addSeparator()
        
        # ソート選択
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["名前", "サイズ", "更新日", "種類"])
        self.sort_combo.currentTextChanged.connect(self.change_sort_order)
        self.toolbar.addWidget(self.sort_combo)
        
        self.toolbar.addSeparator()
        
        # 検索ボックス
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("ファイル名で検索...")
        self.search_box.textChanged.connect(self.filter_files)
        self.toolbar.addWidget(self.search_box)
        
        self.toolbar.addSeparator()
        
        # 隠しファイル表示切替ボタン
        self.hidden_button = QPushButton("👁")
        self.hidden_button.setToolTip("隠しファイル表示切替")
        self.hidden_button.setCheckable(True)
        self.hidden_button.clicked.connect(self.toggle_hidden_files)
        self.toolbar.addWidget(self.hidden_button)

        self.toolbar.addSeparator()

        # 設定ボタン
        self.settings_button = QPushButton("⚙")
        self.settings_button.setToolTip("設定")
        self.settings_button.clicked.connect(self.show_settings)
        self.toolbar.addWidget(self.settings_button)

        self.toolbar.addSeparator()

        # 同一動画検出ボタン
        self.duplicate_video_button = QPushButton("🎬")
        self.duplicate_video_button.setToolTip("同一動画ファイル検出")
        self.duplicate_video_button.clicked.connect(self.show_duplicate_video_dialog)
        self.duplicate_video_button.setEnabled(VIDEO_DIGEST_AVAILABLE)
        self.toolbar.addWidget(self.duplicate_video_button)

        # ファイル検索ボタン
        self.search_button = QPushButton("🔍")
        self.search_button.setToolTip("ファイル検索")
        self.search_button.clicked.connect(self.show_file_search_dialog)
        self.search_button.setEnabled(FILE_SEARCH_AVAILABLE)
        self.toolbar.addWidget(self.search_button)

        # ディスク分析ボタン
        self.disk_analysis_button = QPushButton("📊")
        self.disk_analysis_button.setToolTip("ディスク使用量分析")
        self.disk_analysis_button.clicked.connect(self.show_disk_analysis_dialog)
        self.disk_analysis_button.setEnabled(DISK_ANALYSIS_AVAILABLE)
        self.toolbar.addWidget(self.disk_analysis_button)

        # 選択したファイルをゴミ箱に移動ボタン
        self.move_to_trash_button = QPushButton("🗑️")
        self.move_to_trash_button.setToolTip("選択したファイルをゴミ箱に移動")
        self.move_to_trash_button.clicked.connect(self.move_selected_files_to_trash)
        self.move_to_trash_button.setEnabled(False)
        self.toolbar.addWidget(self.move_to_trash_button)
    
    def setup_models(self):
        """モデルの設定"""
        # 右ペイン用のカスタムファイルシステムモデル（ファイルとフォルダー両方表示）
        self.file_system_model = CustomFileSystemModel()
        self.file_system_model.setRootPath("")
        
        # プロキシモデルの設定（サイズ列を数値でソート可能にする）
        self.proxy_model = FileSortFilterProxyModel()
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.file_system_model)
        
        # リストビューにモデルを設定
        self.list_view.setModel(self.proxy_model)
        
        # 初期パスの設定
        self.update_filter_only()
        self.set_current_path(self.current_path)
    
    def connect_signals(self):
        """シグナルの接続"""
        # 左ペインのフォルダツリーの選択変更
        self.left_pane.tree_view.selectionModel().currentChanged.connect(self.on_tree_selection_changed)
        
        # リストビューのダブルクリック
        self.list_view.doubleClicked.connect(self.on_list_double_clicked)
        
        # リストビューの選択変更
        self.list_view.selectionModel().selectionChanged.connect(self.on_list_selection_changed)
        
        # チェックボックス選択変更時のシグナル接続
        self.proxy_model.dataChanged.connect(self.on_checkbox_selection_changed)
    
    def setup_context_menus(self):
        """コンテキストメニューの設定"""
        # 左ペインのツリービューのコンテキストメニュー
        self.left_pane.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.left_pane.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        
        # リストビューのコンテキストメニュー
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_list_context_menu)
    
    def on_drive_selected(self, drive):
        """ドライブが選択された時の処理"""
        if sys.platform == "win32":
            drive_path = f"{drive}:\\"
        else:
            drive_path = drive
        
        self.set_current_path(drive_path)

    def set_current_path(self, path):
        """現在のパスを設定"""
        self.current_path = path
        # 現在のパスを永続化
        try:
            self.settings.setValue("last_path", path)
        except Exception:
            pass
        self.set_current_path_async(path)
    
    def set_current_path_async(self, path):
        """非同期でパスを設定"""
        # プログレスバーを表示
        self.show_right_progress(f"フォルダを読み込み中: {os.path.basename(path)}")
        
        # QTimerを使用して非同期風に処理
        QTimer.singleShot(100, lambda: self.load_path_sync(path))
    
    def load_path_sync(self, path):
        """同期でパスを読み込み"""
        try:
            # パスの存在確認
            if not os.path.exists(path):
                raise FileNotFoundError(f"フォルダが見つかりません: {path}")
            
            # リストビューのルートを設定（ファイルシステムモデルを使用）
            file_index = self.file_system_model.index(path)
            if file_index.isValid():
                self.list_view.setRootIndex(self.proxy_model.mapFromSource(file_index))
            
            self.hide_right_progress()
            
        except Exception as e:
            self.hide_right_progress()
            QMessageBox.warning(self, "エラー", f"フォルダの読み込みに失敗しました:\n{str(e)}")
    
    
    def on_tree_selection_changed(self, current, previous):
        """ツリービューの選択変更時の処理"""
        if current.isValid() and hasattr(self.left_pane, 'folder_model'):
            path = self.left_pane.folder_model.filePath(current)
            if os.path.isdir(path):
                self.set_current_path(path)
                
                # フォルダ変更時に選択状態をクリア
                self.file_system_model.clear_selection()
                self.move_to_trash_button.setEnabled(False)
    
    def on_list_double_clicked(self, index):
        """リストビューのダブルクリック時の処理"""
        if index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            path = self.file_system_model.filePath(source_index)
            
            if os.path.isdir(path):
                self.set_current_path(path)
                
                # フォルダ変更時に選択状態をクリア
                self.file_system_model.clear_selection()
                self.move_to_trash_button.setEnabled(False)
            else:
                # ファイルの場合はデフォルトアプリケーションで開く
                self.open_file(path)
    
    def on_list_selection_changed(self, selected, deselected):
        """リストビューの選択変更時の処理"""
        # 選択されたファイルの情報をステータスバーに表示（将来実装）
        
        # 動画ファイルが選択された場合の処理
        indexes = self.list_view.selectedIndexes()
        if indexes:
            index = indexes[0]
            source_index = self.proxy_model.mapToSource(index)
            path = self.file_system_model.filePath(source_index)
            
            # 動画ファイルかどうかをチェック
            if self.video_digest_generator and self.video_digest_generator.is_video_file(path):
                # 自動表示設定をチェック
                auto_show = self.settings.value("video_auto_show_digest", False, type=bool)
                if auto_show:
                    # 少し遅延してからダイジェストを表示（連続選択を防ぐため）
                    QTimer.singleShot(500, lambda: self.show_video_digest(path))
    
    def on_checkbox_selection_changed(self, top_left, bottom_right, roles):
        """チェックボックス選択が変更された時の処理"""
        if Qt.CheckStateRole in roles:
            # 選択されたファイル数を取得
            selected_count = self.file_system_model.get_selected_count()
            
            # ゴミ箱移動ボタンの状態を更新
            self.move_to_trash_button.setEnabled(selected_count > 0)
            
            # ステータスバーに選択数を表示
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"選択されたファイル: {selected_count}個")
    
    def show_video_digest(self, video_path):
        """動画ダイジェストを表示"""
        if not VIDEO_DIGEST_AVAILABLE:
            QMessageBox.warning(self, "エラー", "動画ダイジェスト機能が利用できません。OpenCVがインストールされていない可能性があります。")
            return
        
        try:
            dialog = VideoDigestDialog(video_path, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"動画ダイジェストの表示中にエラーが発生しました: {str(e)}")
    
    def show_duplicate_video_dialog(self):
        """同一動画検出ダイアログを表示"""
        if not VIDEO_DIGEST_AVAILABLE:
            QMessageBox.warning(self, "エラー", "同一動画検出機能が利用できません。OpenCVがインストールされていない可能性があります。")
            return
        
        try:
            dialog = DuplicateVideoDialog(self.current_path, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"同一動画検出ダイアログの表示中にエラーが発生しました: {str(e)}")
    
    def show_file_search_dialog(self):
        """ファイル検索ダイアログを表示"""
        if not FILE_SEARCH_AVAILABLE:
            QMessageBox.warning(self, "エラー", "ファイル検索機能が利用できません。")
            return
        
        try:
            dialog = FileSearchDialog(self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ファイル検索ダイアログの表示中にエラーが発生しました: {str(e)}")
    
    def show_disk_analysis_dialog(self):
        """ディスク分析ダイアログを表示"""
        if not DISK_ANALYSIS_AVAILABLE:
            QMessageBox.warning(self, "エラー", "ディスク分析機能が利用できません。")
            return
        
        try:
            # 現在のパスを初期パスとして使用
            dialog = DiskAnalysisDialog(self.current_path, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ディスク分析ダイアログの表示中にエラーが発生しました: {str(e)}")
    
    def move_selected_files_to_trash(self):
        """選択されたファイルをゴミ箱に移動"""
        selected_files = self.file_system_model.get_selected_files()
        
        if not selected_files:
            QMessageBox.information(self, "情報", "移動するファイルが選択されていません。")
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, 
            "確認", 
            f"{len(selected_files)}個のファイルをゴミ箱に移動しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # ゴミ箱移動の実行
        moved_count = 0
        failed_files = []
        
        for file_path in selected_files:
            try:
                if self.move_to_trash(file_path):
                    moved_count += 1
                else:
                    failed_files.append(file_path)
            except Exception as e:
                failed_files.append(f"{file_path} (エラー: {str(e)})")
        
        # 結果を表示
        if moved_count > 0:
            # 選択をクリア
            self.file_system_model.clear_selection()
            self.move_to_trash_button.setEnabled(False)
            
            # ファイルリストを更新
            self.refresh()
            
            message = f"{moved_count}個のファイルをゴミ箱に移動しました。"
            if failed_files:
                message += f"\n\n移動に失敗したファイル:\n" + "\n".join(failed_files)
            
            QMessageBox.information(self, "完了", message)
        else:
            QMessageBox.warning(self, "エラー", "ファイルの移動に失敗しました。")
    
    def move_to_trash(self, file_path):
        """ファイルをゴミ箱に移動"""
        try:
            if sys.platform == "win32":
                # Windowsの場合
                try:
                    import winshell
                    winshell.delete_file(file_path, no_confirm=True, allow_undo=True)
                    return True
                except ImportError:
                    # winshellが利用できない場合は標準的な削除
                    import shutil
                    shutil.move(file_path, os.path.expanduser("~/.local/share/Trash/files/"))
                    return True
            else:
                # macOS/Linuxの場合
                try:
                    import send2trash
                    send2trash.send2trash(file_path)
                    return True
                except ImportError:
                    # send2trashが利用できない場合は標準的な削除
                    import shutil
                    trash_dir = os.path.expanduser("~/.local/share/Trash/files/")
                    os.makedirs(trash_dir, exist_ok=True)
                    shutil.move(file_path, trash_dir)
                    return True
        except Exception as e:
            print(f"ゴミ箱移動エラー ({file_path}): {e}")
            return False
    
    def select_all_files(self):
        """全てのファイルを選択"""
        self.file_system_model.select_all_files()
        self.move_to_trash_button.setEnabled(True)
    
    def clear_file_selection(self):
        """ファイル選択をクリア"""
        self.file_system_model.clear_selection()
        self.move_to_trash_button.setEnabled(False)
    
    def open_file(self, file_path):
        """ファイルをデフォルトアプリケーションで開く"""
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                os.system(f"open '{file_path}'")
            else:
                os.system(f"xdg-open '{file_path}'")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした: {e}")
    
    def show_tree_context_menu(self, position):
        """ツリービューのコンテキストメニューを表示"""
        index = self.left_pane.tree_view.indexAt(position)
        if not index.isValid():
            return
        
        menu = QMenu(self)
        
        # 新規フォルダ作成
        new_folder_action = QAction("新規フォルダ", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        menu.addAction(new_folder_action)
        
        # 更新
        refresh_action = QAction("更新", self)
        refresh_action.triggered.connect(self.refresh)
        menu.addAction(refresh_action)
        
        menu.addSeparator()
        
        # 同一動画検出
        if VIDEO_DIGEST_AVAILABLE:
            duplicate_action = QAction("同一動画ファイル検出", self)
            duplicate_action.triggered.connect(self.show_duplicate_video_dialog)
            menu.addAction(duplicate_action)
        
        menu.addSeparator()
        
        # ディスク分析
        if DISK_ANALYSIS_AVAILABLE:
            disk_analysis_action = QAction("ディスク使用量分析", self)
            disk_analysis_action.triggered.connect(self.show_disk_analysis_dialog)
            menu.addAction(disk_analysis_action)
        
        menu.exec(self.left_pane.tree_view.mapToGlobal(position))
    
    def show_list_context_menu(self, position):
        """リストビューのコンテキストメニューを表示"""
        index = self.list_view.indexAt(position)
        if not index.isValid():
            return
        
        menu = QMenu(self)
        
        # ファイル操作メニュー
        open_action = QAction("開く", self)
        open_action.triggered.connect(self.open_selected_file)
        menu.addAction(open_action)
        
        # 動画ファイルの場合はダイジェスト表示オプションを追加
        source_index = self.proxy_model.mapToSource(index)
        path = self.file_system_model.filePath(source_index)
        if self.video_digest_generator and self.video_digest_generator.is_video_file(path):
            digest_action = QAction("動画ダイジェストを表示", self)
            digest_action.triggered.connect(lambda: self.show_video_digest(path))
            menu.addAction(digest_action)
        
        menu.addSeparator()
        
        copy_action = QAction("コピー", self)
        copy_action.triggered.connect(self.copy_selected_files)
        menu.addAction(copy_action)
        
        cut_action = QAction("切り取り", self)
        cut_action.triggered.connect(self.cut_selected_files)
        menu.addAction(cut_action)
        
        paste_action = QAction("貼り付け", self)
        paste_action.triggered.connect(self.paste_files)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        rename_action = QAction("名前変更", self)
        rename_action.triggered.connect(self.rename_selected_file)
        menu.addAction(rename_action)
        
        delete_action = QAction("削除", self)
        delete_action.triggered.connect(self.delete_selected_files)
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # 選択関連のアクション
        select_all_action = QAction("全て選択", self)
        select_all_action.triggered.connect(self.select_all_files)
        menu.addAction(select_all_action)
        
        clear_selection_action = QAction("選択解除", self)
        clear_selection_action.triggered.connect(self.clear_file_selection)
        menu.addAction(clear_selection_action)
        
        # 選択したファイルをゴミ箱に移動
        move_to_trash_action = QAction("選択したファイルをゴミ箱に移動", self)
        move_to_trash_action.triggered.connect(self.move_selected_files_to_trash)
        move_to_trash_action.setEnabled(self.file_system_model.get_selected_count() > 0)
        menu.addAction(move_to_trash_action)
        
        menu.exec(self.list_view.mapToGlobal(position))
    
    def create_new_folder(self):
        """新規フォルダを作成"""
        folder_name, ok = QInputDialog.getText(
            self, "新規フォルダ", "フォルダ名を入力してください:"
        )
        
        if ok and folder_name:
            try:
                new_folder_path = os.path.join(self.current_path, folder_name)
                os.makedirs(new_folder_path, exist_ok=True)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"フォルダを作成できませんでした: {e}")
    
    def refresh(self):
        """表示を更新"""
        try:
            # 現在のパスを保存
            old_path = self.current_path

            # ファイルシステムモデルの更新
            self.file_system_model.beginResetModel()
            self.file_system_model.endResetModel()

            # 左ペインのフォルダモデルの更新
            if hasattr(self.left_pane, 'folder_model'):
                self.left_pane.folder_model.beginResetModel()
                self.left_pane.folder_model.endResetModel()

            # 現在のパスを再設定（非同期）
            self.set_current_path_async(old_path)

        except Exception as e:
            print(f"更新エラー: {e}")
            # フォールバック
            self.set_current_path_async(self.current_path)
    
    def open_selected_file(self):
        """選択されたファイルを開く"""
        indexes = self.list_view.selectedIndexes()
        if indexes:
            index = indexes[0]
            source_index = self.proxy_model.mapToSource(index)
            path = self.file_system_model.filePath(source_index)
            self.open_file(path)
    
    def copy_selected_files(self):
        """選択されたファイルをコピー"""
        # 将来実装: クリップボードへのコピー
        pass
    
    def cut_selected_files(self):
        """選択されたファイルを切り取り"""
        # 将来実装: クリップボードへの切り取り
        pass
    
    def paste_files(self):
        """ファイルを貼り付け"""
        # 将来実装: クリップボードからの貼り付け
        pass
    
    def rename_selected_file(self):
        """選択されたファイルの名前を変更"""
        indexes = self.list_view.selectedIndexes()
        if not indexes:
            return
        
        index = indexes[0]
        source_index = self.proxy_model.mapToSource(index)
        current_name = self.file_system_model.fileName(source_index)
        
        new_name, ok = QInputDialog.getText(
            self, "名前変更", "新しい名前を入力してください:", text=current_name
        )
        
        if ok and new_name and new_name != current_name:
            try:
                old_path = self.file_system_model.filePath(source_index)
                new_path = os.path.join(os.path.dirname(old_path), new_name)
                os.rename(old_path, new_path)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"名前を変更できませんでした: {e}")
    
    def delete_selected_files(self):
        """選択されたファイルを削除"""
        indexes = self.list_view.selectedIndexes()
        if not indexes:
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, "削除確認", 
            f"{len(indexes)}個のアイテムを削除しますか？\nこの操作は元に戻せません。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                for index in indexes:
                    source_index = self.proxy_model.mapToSource(index)
                    path = self.file_system_model.filePath(source_index)
                    
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"削除できませんでした: {e}")
    
    def navigate_up(self):
        """上のフォルダに移動"""
        parent_path = os.path.dirname(self.current_path)
        if parent_path and parent_path != self.current_path:
            self.set_current_path(parent_path)
    
    def change_view_mode(self, mode):
        """表示モードを変更"""
        try:
            # QListViewかQTreeViewかを確認
            if hasattr(self.list_view, 'setViewMode'):  # QListView
                if mode == "リスト表示" or mode == 0:
                    self.list_view.setViewMode(QListView.ListMode)
                    self.list_view.setHeaderHidden(True)
                    self.view_mode = "list"
                elif mode == "アイコン表示" or mode == 1:
                    self.list_view.setViewMode(QListView.IconMode)
                    self.list_view.setHeaderHidden(True)
                    self.view_mode = "icon"
                else:  # 詳細表示 or mode == 2
                    self.list_view.setViewMode(QListView.ListMode)
                    self.list_view.setHeaderHidden(False)
                    self.view_mode = "detail"
                    self.setup_detail_view()
            else:  # QTreeView
                # QTreeViewの場合はヘッダーの表示/非表示のみ制御
                if mode == "リスト表示" or mode == 0:
                    self.list_view.setHeaderHidden(True)
                    self.view_mode = "list"
                elif mode == "アイコン表示" or mode == 1:
                    self.list_view.setHeaderHidden(True)
                    self.view_mode = "icon"
                else:  # 詳細表示 or mode == 2
                    self.list_view.setHeaderHidden(False)
                    self.view_mode = "detail"
                    self.setup_detail_view()
                
            # 表示モード設定を保存
            self.settings.setValue("view_mode", self.view_mode)
            print(f"表示モードを変更しました: {self.view_mode}")
        except Exception as e:
            print(f"表示モード変更エラー: {e}")
    
    def change_sort_order(self, sort_type):
        """ソート順を変更"""
        if sort_type == "名前":
            self.proxy_model.sort(0, Qt.AscendingOrder)
        elif sort_type == "サイズ":
            self.proxy_model.sort(1, Qt.AscendingOrder)
        elif sort_type == "更新日":
            self.proxy_model.sort(3, Qt.DescendingOrder)
        elif sort_type == "種類":
            self.proxy_model.sort(2, Qt.AscendingOrder)
    
    def filter_files(self, text):
        """ファイルをフィルタリング"""
        if text:
            self.proxy_model.setFilterWildcard(f"*{text}*")
        else:
            self.proxy_model.setFilterWildcard("*")
        
        # フィルタリング後に現在のパスを再設定
        self.set_current_path(self.current_path)

    def toggle_hidden_files(self):
        """隠しファイル表示の切替"""
        self.show_hidden = not self.show_hidden
        self.hidden_button.setChecked(self.show_hidden)

        # 設定を保存
        self.settings.setValue("show_hidden", self.show_hidden)

        # フィルター設定を更新（モデルの再設定は行わない）
        self.update_filter_only()

        # 表示を更新
        self.refresh()

    def update_filter_only(self):
        """フィルター設定のみを更新（モデルの再設定は行わない）"""
        # 基本フィルター
        base_filter = QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot
        folder_filter = QDir.AllDirs | QDir.NoDotAndDotDot

        # 隠しファイル表示が有効な場合はHiddenを追加
        if self.show_hidden:
            base_filter |= QDir.Hidden
            folder_filter |= QDir.Hidden

        # 既存のモデルのフィルターを更新
        self.file_system_model.setFilter(base_filter)
        if hasattr(self.left_pane, 'folder_model'):
            self.left_pane.folder_model.setFilter(folder_filter)

    def setup_custom_delegate(self):
        """カスタムデリゲートの設定"""
        # 右ペイン（ファイル一覧）用のデリゲート
        self.file_delegate = FileItemDelegate(self)
        self.list_view.setItemDelegate(self.file_delegate)

        # 左ペイン（フォルダツリー）用のデリゲート
        if hasattr(self.left_pane, 'tree_view'):
            self.folder_delegate = FileItemDelegate(self)
            self.left_pane.tree_view.setItemDelegate(self.folder_delegate)
    
    def setup_detail_view(self):
        """詳細表示の設定"""
        header = self.list_view.header()
        header.setStretchLastSection(False)
        
        # 列の幅を設定
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名前
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # サイズ
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 種類
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 更新日時
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 権限
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 作成日時
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # 属性
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # 拡張子
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # 所有者
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # グループ
        
        # 列の表示/非表示を設定
        self.update_column_visibility()
    
    def update_column_visibility(self):
        """列の表示/非表示を更新"""
        try:
            print(f"update_column_visibility呼び出し: view_mode={self.view_mode}")
            if self.view_mode == "detail" and hasattr(self, 'list_view'):
                header = self.list_view.header()
                if header and hasattr(self, 'visible_columns'):
                    print(f"列数: {header.count()}, visible_columns: {self.visible_columns}")
                    # 各列の表示/非表示を安全に設定
                    for col_index, key in enumerate(["name", "size", "type", "modified", "permissions", "created", "attributes", "extension", "owner", "group"]):
                        if col_index < header.count():  # 列が存在する場合のみ
                            if col_index == 0:  # 名前列は常に表示
                                header.setSectionHidden(col_index, False)
                                print(f"列{col_index}({key}): 表示 (名前列は常に表示)")
                            elif key in self.visible_columns:
                                should_hide = not self.visible_columns[key]
                                header.setSectionHidden(col_index, should_hide)
                                print(f"列{col_index}({key}): {'非表示' if should_hide else '表示'}")
                    
                    # ヘッダーを強制的に再描画
                    header.update()
                    self.list_view.viewport().update()
                    print(f"列表示を更新完了: {self.visible_columns}")
        except Exception as e:
            print(f"列表示更新エラー: {e}")
    
    def debug_column_state(self):
        """列の状態をデバッグ出力"""
        if hasattr(self, 'list_view') and hasattr(self.list_view, 'header'):
            header = self.list_view.header()
            print("=== 現在の列状態 ===")
            columns = ["name", "size", "type", "modified", "permissions", "created", "attributes", "extension", "owner", "group"]
            for i, col_name in enumerate(columns):
                if i < header.count():
                    hidden = header.isSectionHidden(i)
                    expected = self.visible_columns.get(col_name, False)
                    status = "OK" if (not hidden) == expected else "NG"
                    print(f"  {status} 列{i}({col_name}): {'非表示' if hidden else '表示'} / 期待: {'表示' if expected else '非表示'}")
            print("=" * 20)
    
    def show_settings(self):
        """設定画面を表示"""
        try:
            # 現在の設定を最新に更新してからダイアログに渡す
            current_visible_columns = self.visible_columns.copy()
            dialog = SettingsDialog(self, self.settings, current_visible_columns)
            if dialog.exec() == QDialog.Accepted:
                print("設定ダイアログでOKが押されました")
                
                # まずQSettingsから設定を再読み込み
                self.load_settings()
                print(f"設定を再読み込み: {self.visible_columns}")
                
                # 詳細表示モードに切り替え（列設定を確認できるように）
                if hasattr(self, 'view_mode_combo'):
                    if self.view_mode != "detail":
                        print("詳細表示モードに切り替えます")
                        self.view_mode_combo.setCurrentIndex(2)  # 詳細表示
                        self.change_view_mode(2)
                
                # ファイルシステムモデルに設定を反映
                if hasattr(self, 'file_system_model') and hasattr(self.file_system_model, 'update_visible_columns'):
                    self.file_system_model.update_visible_columns(self.visible_columns)
                    print("ファイルシステムモデルに設定を反映しました")
                
                # 列表示を強制更新
                self.update_column_visibility()
                
                # デバッグ: 列の状態を確認
                self.debug_column_state()
                
                # 設定を保存
                self.save_settings()
                
                print("設定画面での変更を完全に反映しました")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定の適用中にエラーが発生しました: {str(e)}")
    
    def apply_settings(self):
        """設定を適用"""
        try:
            # フォント設定を適用
            if hasattr(self.left_pane, 'tree_view'):
                tree_font = QFont()
                tree_font.setFamily(self.settings.value("tree_font_family", "Arial"))
                tree_font.setPointSize(self.settings.value("tree_font_size", 10, type=int))
                self.left_pane.tree_view.setFont(tree_font)

            if hasattr(self, 'list_view'):
                list_font = QFont()
                list_font.setFamily(self.settings.value("list_font_family", "Arial"))
                list_font.setPointSize(self.settings.value("list_font_size", 10, type=int))
                self.list_view.setFont(list_font)

            # 表示列設定を再読み込み（設定ダイアログからの変更を反映）
            self.visible_columns = {
                "name": True,  # 名前列は常に表示
                "size": self._coerce_bool(self.settings.value("show_size", True), True),
                "type": self._coerce_bool(self.settings.value("show_type", True), True),
                "modified": self._coerce_bool(self.settings.value("show_modified", True), True),
                "permissions": self._coerce_bool(self.settings.value("show_permissions", False), False),
                "created": self._coerce_bool(self.settings.value("show_created", False), False),
                "attributes": self._coerce_bool(self.settings.value("show_attributes", False), False),
                "extension": self._coerce_bool(self.settings.value("show_extension", False), False),
                "owner": self._coerce_bool(self.settings.value("show_owner", False), False),
                "group": self._coerce_bool(self.settings.value("show_group", False), False)
            }

            # 隠しファイル表示設定を適用
            self.show_hidden = self._coerce_bool(self.settings.value("show_hidden", False), False)
            if hasattr(self, 'hidden_button'):
                self.hidden_button.setChecked(self.show_hidden)

            # 表示モード設定を適用
            saved_view_mode = self._coerce_str(self.settings.value("view_mode", "list"), "list")
            if hasattr(self, 'view_mode_combo'):
                mode_map = {"list": 0, "icon": 1, "detail": 2}
                if saved_view_mode in mode_map:
                    self.view_mode_combo.setCurrentIndex(mode_map[saved_view_mode])
                    self.view_mode = saved_view_mode

            # カスタムモデルの表示列設定を更新
            if hasattr(self, 'file_system_model') and hasattr(self.file_system_model, 'update_visible_columns'):
                self.file_system_model.update_visible_columns(self.visible_columns)
            
            # 列の表示を更新（詳細表示の場合）
            if self.view_mode == "detail":
                self.update_column_visibility()

            # デリゲートを更新してファイル色を反映
            if hasattr(self, 'file_delegate'):
                self.list_view.repaint()
            if hasattr(self, 'folder_delegate') and hasattr(self.left_pane, 'tree_view'):
                self.left_pane.tree_view.repaint()
                
            print(f"設定を適用しました: visible_columns={self.visible_columns}, view_mode={self.view_mode}")
        except Exception as e:
            print(f"設定適用エラー: {e}")
    
    def load_settings(self):
        """設定を読み込み"""
        try:
            # 設定値を読み込み（デフォルト値は安全なフォールバックを使用）
            self.visible_columns = {
                "name": True,  # 名前列は常に表示
                "size": self._coerce_bool(self.settings.value("show_size", True), True),
                "type": self._coerce_bool(self.settings.value("show_type", True), True),
                "modified": self._coerce_bool(self.settings.value("show_modified", True), True),
                "permissions": self._coerce_bool(self.settings.value("show_permissions", False), False),
                "created": self._coerce_bool(self.settings.value("show_created", False), False),
                "attributes": self._coerce_bool(self.settings.value("show_attributes", False), False),
                "extension": self._coerce_bool(self.settings.value("show_extension", False), False),
                "owner": self._coerce_bool(self.settings.value("show_owner", False), False),
                "group": self._coerce_bool(self.settings.value("show_group", False), False),
            }

            # 隠しファイル表示設定を読み込み
            self.show_hidden = self._coerce_bool(self.settings.value("show_hidden", False), False)

            # ファイル属性色設定を読み込み
            self.attribute_colors = {
                "hidden": self._coerce_color(self.settings.value("color_hidden", "#808080"), "#808080"),
                "readonly": self._coerce_color(self.settings.value("color_readonly", "#0000FF"), "#0000FF"),
                "system": self._coerce_color(self.settings.value("color_system", "#FF0000"), "#FF0000"),
                "normal": self._coerce_color(self.settings.value("color_normal", "#000000"), "#000000"),
            }
            
            # 表示モード設定を読み込み
            self.view_mode = self._coerce_str(self.settings.value("view_mode", "list"), "list")
            if self.view_mode not in {"list", "icon", "detail"}:
                self.view_mode = "list"
            
            print(f"設定を読み込みました: visible_columns={self.visible_columns}")
        except Exception as e:
            print(f"設定読み込みエラー: {e}")
            # デフォルト設定にフォールバック
            self.visible_columns = {
                "name": True, "size": True, "type": True, "modified": True,
                "permissions": False, "created": False, "attributes": False,
                "extension": False, "owner": False, "group": False
            }
            self.show_hidden = False
            self.attribute_colors = {
                "hidden": "#808080", "readonly": "#0000FF", 
                "system": "#FF0000", "normal": "#000000"
            }
            self.view_mode = "list"
    
    def save_settings(self):
        """設定を保存"""
        try:
            # 表示列設定を保存
            self.settings.setValue("show_name", self.visible_columns.get("name", True))
            self.settings.setValue("show_size", self.visible_columns.get("size", True))
            self.settings.setValue("show_type", self.visible_columns.get("type", True))
            self.settings.setValue("show_modified", self.visible_columns.get("modified", True))
            self.settings.setValue("show_permissions", self.visible_columns.get("permissions", False))
            self.settings.setValue("show_created", self.visible_columns.get("created", False))
            self.settings.setValue("show_attributes", self.visible_columns.get("attributes", False))
            self.settings.setValue("show_extension", self.visible_columns.get("extension", False))
            self.settings.setValue("show_owner", self.visible_columns.get("owner", False))
            self.settings.setValue("show_group", self.visible_columns.get("group", False))

            # 表示モード設定を保存
            self.settings.setValue("view_mode", self.view_mode)
            
            # 隠しファイル表示設定を保存
            self.settings.setValue("show_hidden", self.show_hidden)

        # ファイル属性色設定を保存
            self.settings.setValue("color_hidden", self.attribute_colors.get("hidden", "#808080"))
            self.settings.setValue("color_readonly", self.attribute_colors.get("readonly", "#0000FF"))
            self.settings.setValue("color_system", self.attribute_colors.get("system", "#FF0000"))
            self.settings.setValue("color_normal", self.attribute_colors.get("normal", "#000000"))
            
            # 設定の同期
            self.settings.sync()
            print(f"設定を保存しました: visible_columns={self.visible_columns}")
        except Exception as e:
            print(f"設定保存エラー: {e}")
    
    def show_column_menu(self, position):
        """ヘッダーの右クリックメニューを表示"""
        menu = QMenu(self)
        menu.setTitle("表示する項目")
        
        # 列の定義（表示名、設定キー、列インデックス）
        # 設定ダイアログと同じ項目構成に統一
        columns = [
            ("ファイル名", "name", 0, False),  # 常に表示
            ("サイズ", "size", 1, True),
            ("種類", "type", 2, True),
            ("更新日時", "modified", 3, True),
            ("権限", "permissions", 4, True),
            ("作成日時", "created", 5, True),
            ("属性", "attributes", 6, True),
            ("拡張子", "extension", 7, True),
            ("所有者", "owner", 8, True),
            ("グループ", "group", 9, True),
        ]
        
        # 各列のチェックボックスアクションを作成
        for display_name, key, column_index, can_hide in columns:
            if key in self.visible_columns:
                action = QAction(display_name, self)
                action.setCheckable(True)
                action.setChecked(self.visible_columns[key])
                action.setEnabled(can_hide)  # ファイル名は常に表示
                
                # アクションに列情報を保存
                action.setData({"key": key, "column_index": column_index})
                action.triggered.connect(lambda checked, a=action: self.toggle_column(a))
                menu.addAction(action)
        
        menu.exec(self.list_view.header().mapToGlobal(position))
    
    def toggle_column(self, action):
        """列の表示/非表示を切り替え"""
        try:
            data = action.data()
            key = data["key"]
            column_index = data["column_index"]
            
            # 設定を更新
            self.visible_columns[key] = action.isChecked()
            
            # 設定を保存
            self.settings.setValue(f"show_{key}", action.isChecked())
            
            # カスタムモデルの表示列設定を更新
            if hasattr(self, 'file_system_model') and hasattr(self.file_system_model, 'update_visible_columns'):
                self.file_system_model.update_visible_columns(self.visible_columns)
            
            # 詳細表示の場合は列の表示を更新
            if self.view_mode == "detail":
                self.update_column_visibility()
                
            print(f"列表示を切り替えました: {key}={action.isChecked()}")
        except Exception as e:
            print(f"列切り替えエラー: {e}")


class SettingsDialog(QDialog):
    """設定ダイアログ"""
    
    def __init__(self, parent, settings, visible_columns):
        super().__init__(parent)
        self.settings = settings
        self.visible_columns = visible_columns.copy()
        # デフォルトの色設定を初期化
        self.current_colors = {
            "hidden": "#808080",
            "readonly": "#0000FF",
            "system": "#FF0000",
            "normal": "#000000"
        }
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        # タブウィジェット
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # フォント設定タブ
        font_tab = QWidget()
        font_layout = QFormLayout(font_tab)
        
        # 左ペインフォント
        font_group = QGroupBox("左ペイン（フォルダツリー）")
        font_group_layout = QFormLayout(font_group)
        
        self.tree_font_combo = QFontComboBox()
        self.tree_font_size = QSpinBox()
        self.tree_font_size.setRange(8, 24)
        self.tree_font_size.setValue(10)
        
        font_group_layout.addRow("フォント:", self.tree_font_combo)
        font_group_layout.addRow("サイズ:", self.tree_font_size)
        font_layout.addWidget(font_group)
        
        # 右ペインフォント
        list_font_group = QGroupBox("右ペイン（ファイル一覧）")
        list_font_group_layout = QFormLayout(list_font_group)
        
        self.list_font_combo = QFontComboBox()
        self.list_font_size = QSpinBox()
        self.list_font_size.setRange(8, 24)
        self.list_font_size.setValue(10)
        
        list_font_group_layout.addRow("フォント:", self.list_font_combo)
        list_font_group_layout.addRow("サイズ:", self.list_font_size)
        font_layout.addWidget(list_font_group)
        
        tab_widget.addTab(font_tab, "フォント")
        
        # 表示設定タブ
        display_tab = QWidget()
        display_layout = QFormLayout(display_tab)
        
        # 詳細表示の列設定
        column_group = QGroupBox("詳細表示で表示する項目")
        column_layout = QFormLayout(column_group)
        
        self.name_checkbox = QCheckBox("ファイル名")
        self.name_checkbox.setChecked(True)
        self.name_checkbox.setEnabled(False)  # ファイル名は常に表示
        
        self.size_checkbox = QCheckBox("サイズ")
        self.size_checkbox.setChecked(self.visible_columns["size"])
        
        self.type_checkbox = QCheckBox("種類")
        self.type_checkbox.setChecked(self.visible_columns["type"])
        
        self.modified_checkbox = QCheckBox("更新日時")
        self.modified_checkbox.setChecked(self.visible_columns["modified"])
        
        self.permissions_checkbox = QCheckBox("権限")
        self.permissions_checkbox.setChecked(self.visible_columns["permissions"])
        
        self.created_checkbox = QCheckBox("作成日時")
        self.created_checkbox.setChecked(self.visible_columns["created"])
        
        self.attributes_checkbox = QCheckBox("属性")
        self.attributes_checkbox.setChecked(self.visible_columns["attributes"])
        
        self.extension_checkbox = QCheckBox("拡張子")
        self.extension_checkbox.setChecked(self.visible_columns["extension"])
        
        self.owner_checkbox = QCheckBox("所有者")
        self.owner_checkbox.setChecked(self.visible_columns["owner"])
        
        self.group_checkbox = QCheckBox("グループ")
        self.group_checkbox.setChecked(self.visible_columns["group"])
        
        column_layout.addRow(self.name_checkbox)
        column_layout.addRow(self.size_checkbox)
        column_layout.addRow(self.type_checkbox)
        column_layout.addRow(self.modified_checkbox)
        column_layout.addRow(self.permissions_checkbox)
        column_layout.addRow(self.created_checkbox)
        column_layout.addRow(self.attributes_checkbox)
        column_layout.addRow(self.extension_checkbox)
        column_layout.addRow(self.owner_checkbox)
        column_layout.addRow(self.group_checkbox)
        
        display_layout.addWidget(column_group)
        
        tab_widget.addTab(display_tab, "表示")

        # 色設定タブ
        color_tab = QWidget()
        color_layout = QFormLayout(color_tab)

        color_group = QGroupBox("ファイル属性の色設定")
        color_group_layout = QFormLayout(color_group)

        # 隠しファイル色設定
        self.hidden_color_button = QPushButton()
        self.hidden_color_button.setFixedSize(50, 25)
        self.hidden_color_button.clicked.connect(lambda: self.choose_color('hidden'))

        # 読み込み専用ファイル色設定
        self.readonly_color_button = QPushButton()
        self.readonly_color_button.setFixedSize(50, 25)
        self.readonly_color_button.clicked.connect(lambda: self.choose_color('readonly'))

        # システムファイル色設定
        self.system_color_button = QPushButton()
        self.system_color_button.setFixedSize(50, 25)
        self.system_color_button.clicked.connect(lambda: self.choose_color('system'))

        # 通常ファイル色設定
        self.normal_color_button = QPushButton()
        self.normal_color_button.setFixedSize(50, 25)
        self.normal_color_button.clicked.connect(lambda: self.choose_color('normal'))

        color_group_layout.addRow("隠しファイル:", self.hidden_color_button)
        color_group_layout.addRow("読み込み専用:", self.readonly_color_button)
        color_group_layout.addRow("システムファイル:", self.system_color_button)
        color_group_layout.addRow("通常ファイル:", self.normal_color_button)

        color_layout.addWidget(color_group)
        tab_widget.addTab(color_tab, "色設定")

        # 動画ダイジェスト設定タブ
        video_tab = QWidget()
        video_layout = QFormLayout(video_tab)

        video_group = QGroupBox("動画ダイジェスト設定")
        video_group_layout = QFormLayout(video_group)
        
        # OpenCVが利用できない場合の警告
        if not VIDEO_DIGEST_AVAILABLE:
            warning_label = QLabel("⚠️ 動画ダイジェスト機能は利用できません。\nOpenCVがインストールされていない可能性があります。\n'pip install opencv-python'を実行してください。")
            warning_label.setStyleSheet("color: red; font-weight: bold;")
            warning_label.setWordWrap(True)
            video_group_layout.addRow(warning_label)

        # サムネイル数の設定
        self.thumbnail_count_spin = QSpinBox()
        self.thumbnail_count_spin.setRange(1, 12)
        self.thumbnail_count_spin.setValue(6)
        self.thumbnail_count_spin.setToolTip("生成するサムネイルの数（1-12）")
        self.thumbnail_count_spin.setEnabled(VIDEO_DIGEST_AVAILABLE)
        video_group_layout.addRow("サムネイル数:", self.thumbnail_count_spin)

        # サムネイルサイズの設定
        size_layout = QHBoxLayout()
        self.thumbnail_width_spin = QSpinBox()
        self.thumbnail_width_spin.setRange(80, 400)
        self.thumbnail_width_spin.setValue(160)
        self.thumbnail_width_spin.setSuffix(" px")
        self.thumbnail_width_spin.setToolTip("サムネイルの幅")
        self.thumbnail_width_spin.setEnabled(VIDEO_DIGEST_AVAILABLE)
        
        self.thumbnail_height_spin = QSpinBox()
        self.thumbnail_height_spin.setRange(60, 300)
        self.thumbnail_height_spin.setValue(90)
        self.thumbnail_height_spin.setSuffix(" px")
        self.thumbnail_height_spin.setToolTip("サムネイルの高さ")
        self.thumbnail_height_spin.setEnabled(VIDEO_DIGEST_AVAILABLE)
        
        size_layout.addWidget(QLabel("幅:"))
        size_layout.addWidget(self.thumbnail_width_spin)
        size_layout.addWidget(QLabel("高さ:"))
        size_layout.addWidget(self.thumbnail_height_spin)
        size_layout.addStretch()
        
        video_group_layout.addRow("サムネイルサイズ:", size_layout)

        # 自動表示の設定
        self.auto_show_digest_checkbox = QCheckBox("動画ファイル選択時に自動でダイジェストを表示")
        self.auto_show_digest_checkbox.setToolTip("動画ファイルを選択した際に自動的にダイジェストポップアップを表示するかどうか")
        self.auto_show_digest_checkbox.setEnabled(VIDEO_DIGEST_AVAILABLE)
        video_group_layout.addRow(self.auto_show_digest_checkbox)

        video_layout.addWidget(video_group)
        tab_widget.addTab(video_tab, "動画ダイジェスト")

        # ボタン
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """現在の設定を読み込み"""
        # フォント設定
        tree_font_family = self.settings.value("tree_font_family", "Arial")
        tree_font_size = self.settings.value("tree_font_size", 10, type=int)
        
        self.tree_font_combo.setCurrentFont(QFont(tree_font_family))
        self.tree_font_size.setValue(tree_font_size)
        
        list_font_family = self.settings.value("list_font_family", "Arial")
        list_font_size = self.settings.value("list_font_size", 10, type=int)
        
        self.list_font_combo.setCurrentFont(QFont(list_font_family))
        self.list_font_size.setValue(list_font_size)
        
        # 親ウィジェットから最新の表示列設定を取得
        parent = self.parent()
        if parent and hasattr(parent, 'visible_columns'):
            self.visible_columns = parent.visible_columns.copy()
        
        # 表示列設定
        self.size_checkbox.setChecked(self.visible_columns.get("size", True))
        self.type_checkbox.setChecked(self.visible_columns.get("type", True))
        self.modified_checkbox.setChecked(self.visible_columns.get("modified", True))
        self.permissions_checkbox.setChecked(self.visible_columns.get("permissions", False))
        self.created_checkbox.setChecked(self.visible_columns.get("created", False))
        self.attributes_checkbox.setChecked(self.visible_columns.get("attributes", False))
        self.extension_checkbox.setChecked(self.visible_columns.get("extension", False))
        self.owner_checkbox.setChecked(self.visible_columns.get("owner", False))
        self.group_checkbox.setChecked(self.visible_columns.get("group", False))

        # 動画ダイジェスト設定を読み込み
        self.thumbnail_count_spin.setValue(self.settings.value("video_thumbnail_count", 6, type=int))
        self.thumbnail_width_spin.setValue(self.settings.value("video_thumbnail_width", 160, type=int))
        self.thumbnail_height_spin.setValue(self.settings.value("video_thumbnail_height", 90, type=int))
        self.auto_show_digest_checkbox.setChecked(self.settings.value("video_auto_show_digest", False, type=bool))

        # 色設定を読み込み
        parent = self.parent()
        if parent and hasattr(parent, 'attribute_colors'):
            self.current_colors = parent.attribute_colors.copy()
            self.update_color_buttons()
        else:
            # デフォルトの色設定を初期化
            self.current_colors = {
                "hidden": "#808080",
                "readonly": "#0000FF",
                "system": "#FF0000",
                "normal": "#000000"
            }
            if hasattr(self, 'update_color_buttons'):
                self.update_color_buttons()

    def update_color_buttons(self):
        """色ボタンの表示を更新"""
        if hasattr(self, 'current_colors'):
            if hasattr(self, 'hidden_color_button'):
                self.hidden_color_button.setStyleSheet(f"background-color: {self.current_colors['hidden']}")
            if hasattr(self, 'readonly_color_button'):
                self.readonly_color_button.setStyleSheet(f"background-color: {self.current_colors['readonly']}")
            if hasattr(self, 'system_color_button'):
                self.system_color_button.setStyleSheet(f"background-color: {self.current_colors['system']}")
            if hasattr(self, 'normal_color_button'):
                self.normal_color_button.setStyleSheet(f"background-color: {self.current_colors['normal']}")

    def choose_color(self, attribute_type):
        """色選択ダイアログを表示"""
        if hasattr(self, 'current_colors') and attribute_type in self.current_colors:
            current_color = QColor(self.current_colors[attribute_type])
            color = QColorDialog.getColor(current_color, self, f"{attribute_type}ファイルの色を選択")

            if color.isValid():
                self.current_colors[attribute_type] = color.name()
                self.update_color_buttons()
    
    def accept(self):
        """OKボタンが押された時の処理"""
        # フォント設定を保存
        tree_font = self.tree_font_combo.currentFont()
        self.settings.setValue("tree_font_family", tree_font.family())
        self.settings.setValue("tree_font_size", self.tree_font_size.value())
        
        list_font = self.list_font_combo.currentFont()
        self.settings.setValue("list_font_family", list_font.family())
        self.settings.setValue("list_font_size", self.list_font_size.value())
        
        # 表示列設定を保存
        self.settings.setValue("show_name", True)  # 常にTrue
        self.settings.setValue("show_size", self.size_checkbox.isChecked())
        self.settings.setValue("show_type", self.type_checkbox.isChecked())
        self.settings.setValue("show_modified", self.modified_checkbox.isChecked())
        self.settings.setValue("show_permissions", self.permissions_checkbox.isChecked())
        self.settings.setValue("show_created", self.created_checkbox.isChecked())
        self.settings.setValue("show_attributes", self.attributes_checkbox.isChecked())
        self.settings.setValue("show_extension", self.extension_checkbox.isChecked())
        self.settings.setValue("show_owner", self.owner_checkbox.isChecked())
        self.settings.setValue("show_group", self.group_checkbox.isChecked())
        
        # 設定を即座に同期
        self.settings.sync()
        print("QSettingsに表示設定を保存しました")
        
        # 親ウィジェットのvisible_columnsを即座に更新
        parent = self.parent()
        if parent and hasattr(parent, 'visible_columns'):
            parent.visible_columns = {
                "name": True,
                "size": self.size_checkbox.isChecked(),
                "type": self.type_checkbox.isChecked(),
                "modified": self.modified_checkbox.isChecked(),
                "permissions": self.permissions_checkbox.isChecked(),
                "created": self.created_checkbox.isChecked(),
                "attributes": self.attributes_checkbox.isChecked(),
                "extension": self.extension_checkbox.isChecked(),
                "owner": self.owner_checkbox.isChecked(),
                "group": self.group_checkbox.isChecked()
            }
            print(f"親ウィジェットのvisible_columnsを更新: {parent.visible_columns}")
            
            # ファイルシステムモデルにも即座に反映
            if hasattr(parent, 'file_system_model') and hasattr(parent.file_system_model, 'update_visible_columns'):
                parent.file_system_model.update_visible_columns(parent.visible_columns)
                print("ファイルシステムモデルの設定も更新しました")
                
            # 詳細表示の場合は列表示を即座に更新
            if hasattr(parent, 'view_mode') and parent.view_mode == "detail":
                if hasattr(parent, 'update_column_visibility'):
                    parent.update_column_visibility()
                    print("列表示を即座に更新しました")

        # 動画ダイジェスト設定を保存
        self.settings.setValue("video_thumbnail_count", self.thumbnail_count_spin.value())
        self.settings.setValue("video_thumbnail_width", self.thumbnail_width_spin.value())
        self.settings.setValue("video_thumbnail_height", self.thumbnail_height_spin.value())
        self.settings.setValue("video_auto_show_digest", self.auto_show_digest_checkbox.isChecked())

        # 色設定を保存
        parent = self.parent()
        if parent and hasattr(self, 'current_colors'):
            parent.attribute_colors = self.current_colors.copy()
            self.settings.setValue("color_hidden", self.current_colors["hidden"])
            self.settings.setValue("color_readonly", self.current_colors["readonly"])
            self.settings.setValue("color_system", self.current_colors["system"])
            self.settings.setValue("color_normal", self.current_colors["normal"])
        elif parent:
            # current_colorsが存在しない場合はデフォルト値を保存
            default_colors = {
                "hidden": "#808080",
                "readonly": "#0000FF", 
                "system": "#FF0000",
                "normal": "#000000"
            }
            parent.attribute_colors = default_colors.copy()
            self.settings.setValue("color_hidden", default_colors["hidden"])
            self.settings.setValue("color_readonly", default_colors["readonly"])
            self.settings.setValue("color_system", default_colors["system"])
            self.settings.setValue("color_normal", default_colors["normal"])

        super().accept()


class FileItemDelegate(QStyledItemDelegate):
    """ファイル属性に基づいてアイテムの表示を変更するカスタムデリゲート"""

    def __init__(self, file_manager, parent=None):
        super().__init__(parent)
        self.file_manager = file_manager

    def paint(self, painter, option, index):
        """アイテムの描画"""
        # デフォルトの描画を実行
        super().paint(painter, option, index)

        # ファイル情報を取得
        if hasattr(self.file_manager, 'file_system_model') and hasattr(self.file_manager, 'folder_model'):
            model = index.model()

            # プロキシモデルの場合はソースモデルのインデックスを取得
            if hasattr(model, 'mapToSource'):
                source_index = model.mapToSource(index)
                file_path = self.file_manager.file_system_model.filePath(source_index)
            elif model == self.file_manager.folder_model:
                file_path = self.file_manager.folder_model.filePath(index)
            elif model == self.file_manager.file_system_model:
                file_path = self.file_manager.file_system_model.filePath(index)
            else:
                return

            # ファイル情報を取得
            file_info = QFileInfo(file_path)
            if not file_info.exists():
                return

            # ファイル属性に基づいて色を決定
            color = self.get_file_color(file_info)

            if color != self.file_manager.attribute_colors["normal"]:
                # テキスト色を変更
                painter.save()
                painter.setPen(QColor(color))

                # テキストを再描画
                text = index.data(Qt.DisplayRole)
                if text:
                    text_rect = option.rect
                    text_rect.setLeft(text_rect.left() + 5)  # 少し右にずらす
                    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, str(text))

                painter.restore()

    def get_file_color(self, file_info):
        """ファイル属性に基づいて色を決定"""
        # 隠しファイルかチェック（Unixライクシステムでは.で始まるファイル）
        if file_info.fileName().startswith('.') and file_info.fileName() not in ['.', '..']:
            return self.file_manager.attribute_colors["hidden"]

        # Windowsの場合の隠しファイル属性チェック
        if sys.platform == "win32":
            import stat
            try:
                file_stat = os.stat(file_info.filePath())
                if file_stat.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN:
                    return self.file_manager.attribute_colors["hidden"]
                if file_stat.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM:
                    return self.file_manager.attribute_colors["system"]
            except (AttributeError, OSError):
                pass

        # 読み込み専用ファイルかチェック
        if not file_info.isWritable() and file_info.isReadable():
            return self.file_manager.attribute_colors["readonly"]

        # デフォルト色
        return self.file_manager.attribute_colors["normal"]


# モジュールとして使用する場合のテスト用
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    widget = FileManagerWidget()
    widget.show()
    sys.exit(app.exec())
