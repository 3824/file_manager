from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QModelIndex, Signal, QSortFilterProxyModel, QFileInfo, QObject, QTimer
from PySide6.QtWidgets import QFileSystemModel
from PySide6.QtGui import QColor

_VIDEO_EXTENSIONS = frozenset({
    'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v', '3gp', 'mpg', 'mpeg'
})

from .logger import logger

@dataclass
class RenameSummary:
    """一括リネーム結果。"""
    renamed_count: int = 0
    skipped_count: int = 0
    error_messages: list[str] = field(default_factory=list)

class CustomFileSystemModel(QFileSystemModel):
    """カスタムファイルシステムモデル（追加列対応）"""

    metadata_fetch_requested = Signal(str) # パス

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
            "group": False,
            "duration": True,
            "resolution": True,
            "fps": False
        }
        self.metadata_cache = {}
        self.metadata_loading = set()
        # 取得失敗ファイル: {path: failed_at_timestamp}。60秒間は再リクエストしない
        self.metadata_failed: dict[str, float] = {}
        # 永続キャッシュ（遅延初期化）: None=未初期化, instance=利用可能
        self._persistent_cache = None
        self._persistent_cache_ready = False  # 初期化試行済みフラグ
    
    def columnCount(self, parent=QModelIndex()):
        """列数を返す"""
        return 13  # 名前、サイズ、種類、更新日時、権限、作成日時、属性、拡張子、所有者、グループ, 再生時間, 解像度, FPS
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """ヘッダーデータを返す"""
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            headers = [
                "名前", "サイズ", "種類", "更新日時", "権限", 
                "作成日時", "属性", "拡張子", "所有者", "グループ",
                "再生時間", "解像度", "FPS"
            ]
            if 0 <= section < len(headers):
                return headers[section]
        return super().headerData(section, orientation, role)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        file_info = self.fileInfo(index)
        column = index.column()

        # 標準列（0-3）は親クラスの実装を使用
        if column < 4:
            return super().data(index, role)
        
        # カスタム列の実装
        if role == Qt.DisplayRole:
            if column == 4:  # 権限
                # PySide6 6.x で QFileInfo.Permission が廃止されているため、
                # 非表示時はデータ取得を完全にスキップしてログ汚染を防ぐ
                if not self.visible_columns.get("permissions", False):
                    return None
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
                if not self.visible_columns.get("owner", False):
                    return None
                return self.get_owner(file_info)
            elif column == 9:  # グループ
                if not self.visible_columns.get("group", False):
                    return None
                return self.get_group(file_info)
            elif column == 10: # 再生時間
                meta = self.get_video_metadata(file_info)
                if isinstance(meta, dict):
                    duration = meta.get('duration', 0)
                    m, s = divmod(int(duration), 60)
                    h, m = divmod(m, 60)
                    return f"{h:02}:{m:02}:{s:02}"
                return None
            elif column == 11: # 解像度
                meta = self.get_video_metadata(file_info)
                if isinstance(meta, dict):
                    return f"{meta.get('width', 0)}x{meta.get('height', 0)}"
                return None
            elif column == 12: # FPS
                meta = self.get_video_metadata(file_info)
                if isinstance(meta, dict):
                    return f"{meta.get('fps', 0):.2f}"
                return None
        
        return None

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
        except Exception as e:
            logger.debug(f"Failed to get permissions: {e}")
            return "---------"

    def get_video_metadata(self, file_info):
        """動画メタデータを取得（キャッシュまたは非同期取得）"""
        if file_info.suffix().lower() not in _VIDEO_EXTENSIONS:
            return None

        path = file_info.absoluteFilePath()

        if path in self.metadata_cache:
            return self.metadata_cache[path]

        # 60秒以内に失敗済みのファイルは再リクエストしない
        failed_at = self.metadata_failed.get(path)
        if failed_at is not None and time.monotonic() - failed_at < 60.0:
            return None

        # 永続キャッシュ（SQLite）を確認
        cached = self._get_from_persistent_cache(path)
        if cached is not None:
            self.metadata_cache[path] = cached
            return cached

        if path not in self.metadata_loading:
            self.request_metadata_fetch(path)
            self.metadata_loading.add(path)

        return None

    def _ensure_persistent_cache(self) -> None:
        """永続キャッシュを遅延初期化する（初回のみ試行）。"""
        if self._persistent_cache_ready:
            return
        self._persistent_cache_ready = True
        try:
            from .video_metadata_cache import VideoMetadataCache
            c = VideoMetadataCache()
            c.cleanup()
            self._persistent_cache = c
        except Exception as e:
            logger.debug(f"Persistent metadata cache unavailable: {e}")

    def _get_from_persistent_cache(self, path: str):
        """永続キャッシュから取得。ヒットした場合のみ dict を返す。"""
        self._ensure_persistent_cache()
        if self._persistent_cache is None:
            return None
        try:
            st = os.stat(path)
            return self._persistent_cache.get(path, st.st_mtime_ns, st.st_size)
        except Exception:
            return None

    def request_metadata_fetch(self, path):
        """メタデータ取得リクエストを発行"""
        if hasattr(self, 'metadata_fetch_requested'):
            self.metadata_fetch_requested.emit(path)

    def update_metadata(self, path, metadata):
        """非同期取得完了後のコールバック"""
        self.metadata_loading.discard(path)

        # 失敗判定: None / 非dict / "error" キーを含む dict はすべて失敗扱い
        if not isinstance(metadata, dict) or "error" in metadata:
            self.metadata_failed[path] = time.monotonic()
            return

        self.metadata_failed.pop(path, None)
        self.metadata_cache[path] = metadata

        # 永続キャッシュに書き込む
        self._ensure_persistent_cache()
        if self._persistent_cache is not None:
            try:
                st = os.stat(path)
                self._persistent_cache.put(path, st.st_mtime_ns, st.st_size, metadata)
            except Exception as e:
                logger.debug(f"Persistent cache write error: {e}")

        index = self.index(path)
        if index.isValid():
            self.dataChanged.emit(
                index.sibling(index.row(), 10),
                index.sibling(index.row(), 12),
                [Qt.DisplayRole],
            )
    
    def get_attributes(self, file_info):
        """属性文字列を取得"""
        attributes = []
        
        if file_info.isHidden():
            attributes.append("隠し")
        if not file_info.isWritable():
            attributes.append("読み取り専用")
        if file_info.isSymLink():
            attributes.append("シンボリックリンク")
        
        return ", ".join(attributes) if attributes else "通常"
    
    def get_owner(self, file_info):
        """所有者を取得"""
        try:
            path = file_info.absoluteFilePath()
            if sys.platform != "win32":
                import pwd
                stat_info = os.stat(path, follow_symlinks=False)
                owner = pwd.getpwuid(stat_info.st_uid).pw_name
                return owner
            else:
                return "User"
        except Exception as e:
            logger.debug(f"Failed to get owner for {file_info.absoluteFilePath()}: {e}")
            return "Unknown"
    
    def get_group(self, file_info):
        """グループを取得"""
        try:
            path = file_info.absoluteFilePath()
            if sys.platform != "win32":
                import grp
                stat_info = os.stat(path, follow_symlinks=False)
                group = grp.getgrgid(stat_info.st_gid).gr_name
                return group
            else:
                return "Users"
        except Exception as e:
            logger.debug(f"Failed to get group for {file_info.absoluteFilePath()}: {e}")
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
        try:
            self.visible_columns = visible_columns.copy()
        except Exception as e:
            logger.error(f"Failed to copy visible_columns: {e}")
            self.visible_columns = dict(visible_columns)

        def _reset():
            try:
                self.beginResetModel()
                self.endResetModel()
            except Exception as e:
                logger.error(f"Error during model reset: {e}")
                try:
                    self.layoutChanged.emit()
                except Exception:
                    pass

        QTimer.singleShot(0, _reset)

class FileSortFilterProxyModel(QSortFilterProxyModel):
    """サイズ列ソートとファイル名フィルターを扱うプロキシモデル"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filename_filter_text = ""
        self._foreign_filename_only = False
        self._tag_filter_tags: list = []
        self._tag_filter_paths: "set | None" = None

    def _change_filter(self, update_callback) -> None:
        """Qt 6.9 未満では beginFilterChange が無いため互換処理に戻す。"""
        if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
            self.beginFilterChange()
            try:
                update_callback()
            finally:
                self.endFilterChange()
            return

        update_callback()
        self.invalidateFilter()

    def set_filename_filter_text(self, text):
        """ファイル名検索文字列を設定する。"""
        self._change_filter(lambda: setattr(self, "_filename_filter_text", (text or "").casefold()))

    def set_foreign_filename_only(self, enabled):
        """外国語と思われるファイル名のみ表示するかを設定する。"""
        self._change_filter(lambda: setattr(self, "_foreign_filename_only", bool(enabled)))

    def set_tag_filter(self, tags: list, matching_paths: "set | None") -> None:
        """タグフィルタを設定する。tags が空なら解除。"""
        def _update() -> None:
            self._tag_filter_tags = list(tags)
            self._tag_filter_paths = matching_paths

        self._change_filter(_update)

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        if source_model is None:
            return True

        index = source_model.index(source_row, 0, source_parent)
        if not index.isValid():
            return True

        try:
            file_info = source_model.fileInfo(index)
            name = file_info.fileName()
        except Exception as e:
            logger.debug(f"Error getting fileInfo for filter: {e}")
            name = str(source_model.data(index) or "")
            file_info = None

        if file_info is not None and file_info.isDir():
            return True

        if self._filename_filter_text and self._filename_filter_text not in name.casefold():
            return False

        if self._foreign_filename_only and not self._looks_like_foreign_filename(name, file_info):
            return False

        if self._tag_filter_paths is not None and file_info is not None and not file_info.isDir():
            try:
                full_path = file_info.absoluteFilePath()
                if full_path not in self._tag_filter_paths:
                    return False
            except Exception:
                pass

        return True

    @classmethod
    def _looks_like_foreign_filename(cls, name, file_info=None):
        """日本語名ではない可能性が高いファイル名を簡易判定する。"""
        if file_info is not None and file_info.isDir():
            return False

        stem = os.path.splitext(name)[0]
        if not stem:
            return False

        # 漢字だけでは日本語と中国語を確実に区別できない。誤って日本語名を
        # 一括翻訳しないよう、漢字のみの場合は簡体字の強い手掛かりがある時だけ
        # 外国語候補とする。
        simplified_chinese_hints = frozenset(
            "这为发后时说们对过动经从实进产长业东书门见开关录议"
        )
        has_foreign_letter = False
        has_cjk = False
        for char in stem:
            code = ord(char)
            if cls._is_japanese_character(code):
                return False
            if 0x3400 <= code <= 0x9FFF:
                has_cjk = True
            elif char.isalpha():
                has_foreign_letter = True

        return has_foreign_letter or (
            has_cjk and any(char in simplified_chinese_hints for char in stem)
        )

    @staticmethod
    def _is_japanese_character(code):
        return (
            0x3040 <= code <= 0x30FF
        )

    @staticmethod
    def _created_datetime(file_info):
        if hasattr(file_info, "birthTime"):
            created = file_info.birthTime()
            if created.isValid():
                return created
        if hasattr(file_info, "created"):
            created = file_info.created()
            if created.isValid():
                return created
        return file_info.lastModified()

    def lessThan(self, left, right):
        try:
            source_model = self.sourceModel()
            if left.column() == right.column() and hasattr(source_model, 'fileInfo'):
                # サイズ列と日付列は表示文字列ではなく実値で比較する。
                column = left.column()
                left_info = source_model.fileInfo(left)
                right_info = source_model.fileInfo(right)

                if column == 1:
                    left_size = left_info.size() if left_info.isFile() else 0
                    right_size = right_info.size() if right_info.isFile() else 0

                    return left_size < right_size

                if column == 3:
                    return (
                        left_info.lastModified().toMSecsSinceEpoch()
                        < right_info.lastModified().toMSecsSinceEpoch()
                    )

                if column == 5:
                    return (
                        self._created_datetime(left_info).toMSecsSinceEpoch()
                        < self._created_datetime(right_info).toMSecsSinceEpoch()
                    )
        except Exception as e:
            logger.debug(f"Error in lessThan comparison: {e}")

        return super().lessThan(left, right)

class VideoMetadataWorker(QObject):
    """動画メタデータを非同期で取得するワーカー"""
    metadata_ready = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 動的にインポートして循環参照を防ぐ
        from .video_digest import VideoDigestGenerator
        self.generator = VideoDigestGenerator()

    def fetch_metadata(self, path):
        """メタデータを取得してシグナルで返す"""
        try:
            info = self.generator.get_video_info(path)
            if info:
                self.metadata_ready.emit(path, info)
            else:
                self.metadata_ready.emit(path, {"error": "Failed"})
        except Exception as e:
            logger.error(f"Error fetching video metadata for {path}: {e}")
            self.metadata_ready.emit(path, {"error": str(e)})
