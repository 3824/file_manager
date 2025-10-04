"""
ファイルマネージャーパッケージ
"""

from .file_manager import FileManagerWidget
from .file_search_dialog import FileSearchDialog
from .disk_analysis_dialog import DiskAnalysisDialog
from . import main as main_module
from .video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
from .video_digest_dialog import VideoDigestDialog
from .video_duplicates import DuplicateGroup, find_duplicate_videos
from .video_duplicates_dialog import VideoDuplicatesDialog
from .video_thumbnail_preview import VideoThumbnailPreview

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
    "VideoDuplicatesDialog",
    "find_duplicate_videos",
    "DuplicateGroup",
]



