"""
ファイルマネージャーパッケージ
"""

# OpenCV / FFmpeg のログを抑制（破損動画の moov atom not found 等を出さない）。
# cv2 を最初に import する前に設定する必要があるためここに置く。
import os as _os

_os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
_os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
_os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

# Windows (Python 3.8+) では PySide6 の multimedia plugin DLL が
# デフォルトの検索パスに含まれないため明示的に追加する。
# これを行わないと "No QtMultimedia backends found" エラーになる。
if hasattr(_os, "add_dll_directory"):
    import sysconfig as _sysconfig
    _pyside6_dir = _os.path.join(_sysconfig.get_path("purelib"), "PySide6")
    if _os.path.isdir(_pyside6_dir):
        _os.add_dll_directory(_pyside6_dir)
    del _sysconfig, _pyside6_dir

try:
    import cv2 as _cv2

    if hasattr(_cv2, "setLogLevel") and hasattr(_cv2, "LOG_LEVEL_SILENT"):
        _cv2.setLogLevel(_cv2.LOG_LEVEL_SILENT)
except Exception:
    pass

from .file_manager import FileManagerWidget
from .file_search_dialog import FileSearchDialog
from .disk_analysis_dialog import DiskAnalysisDialog
from . import main as main_module
from .video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
from .video_digest_dialog import VideoDigestDialog
from .video_duplicates import DuplicateGroup, find_duplicate_videos
from .video_duplicates_dialog import VideoDuplicatesDialog
from .video_thumbnail_preview import VideoThumbnailPreview
from .video_player_widget import VideoPlayerWidget
from .video_player_window import VideoPlayerWindow
from .filename_similarity import SimilarFileGroup, find_similar_filenames
from .filename_similarity_dialog import FilenameSimilarityDialog
from .filename_translation import FilenameTranslationService, TranslationRenameCandidate
from .translate_preview_dialog import TranslatePreviewDialog
from .video_digest_cache import VideoDigestCache

# パッケージ直下で main モジュールを読み込み、run スクリプト等から参照できるようにする
main = main_module

def run_main(*args, **kwargs):
    """Convenience wrapper forwarding to file_manager.main.main."""
    return main_module.main(*args, **kwargs)


__all__ = [
    "FileManagerWidget",
    "main",
    "run_main",
    "FileSearchDialog",
    "DiskAnalysisDialog",
    "VideoDigestGenerator",
    "OPENCV_AVAILABLE",
    "VideoDigestDialog",
    "VideoThumbnailPreview",
    "VideoPlayerWidget",
    "VideoPlayerWindow",
    "VideoDuplicatesDialog",
    "find_duplicate_videos",
    "DuplicateGroup",
    "FilenameSimilarityDialog",
    "find_similar_filenames",
    "SimilarFileGroup",
    "FilenameTranslationService",
    "TranslationRenameCandidate",
    "TranslatePreviewDialog",
    "VideoDigestCache",
]



