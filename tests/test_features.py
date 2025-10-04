import os
import sys
import importlib
import types
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager import video_digest
from file_manager.file_manager import SettingsDialog, FileManagerWidget, CustomFileSystemModel
from PySide6.QtCore import QSettings, Qt


def test_video_digest_fallback_emits_digest(qtbot, tmp_path):
    """OpenCVが無い環境でもプレースホルダーを返してdigest_generatedを発行する"""
    # Ensure OPENCV_AVAILABLE is False for this test
    monkey_cv = False
    # temporarily override flag
    orig_flag = video_digest.OPENCV_AVAILABLE
    video_digest.OPENCV_AVAILABLE = False

    generator = video_digest.VideoDigestGenerator()

    received = []
    def on_digest(path, thumbs):
        received.append((path, thumbs))

    generator.digest_generated.connect(on_digest)

    # Create a fake small file to pass is_video_file check
    f = tmp_path / "test.mp4"
    f.write_text('dummy')

    # run generation (synchronous path for fallback)
    generator.generate_digest(str(f), max_thumbnails=2, thumbnail_size=(10, 10))

    # restore flag
    video_digest.OPENCV_AVAILABLE = orig_flag

    assert len(received) == 1
    path, thumbs = received[0]
    assert path == str(f)
    assert isinstance(thumbs, list)
    assert len(thumbs) == 2


def test_settings_accept_does_not_crash(qtbot, monkeypatch):
    """SettingsDialog.accept should not raise even if parent updates fail"""
    # Create a parent that intentionally raises on update to simulate edge case
    class BadParent:
        def __init__(self):
            self.visible_columns = {}
            self.file_system_model = None
            self.view_mode = 'list'
        def __getattr__(self, name):
            # any attribute access other than existing ones will raise
            raise RuntimeError("parent failure")

    parent = BadParent()

    called = {}

    def dummy_message(self):
        called['invoked'] = True

    monkeypatch.setattr(SettingsDialog, '_show_save_success_message', dummy_message)

    dialog = SettingsDialog(parent, QSettings('FileManager', 'Settings'), parent.visible_columns)

    # calling accept should not raise
    dialog.accept()

    assert called.get('invoked')


def test_search_button_dynamic_import(qtbot, monkeypatch):
    """Clicking the toolbar search button should attempt to load the dialog dynamically and call exec"
    """
    # create a fake module object and insert into sys.modules
    mod = types.ModuleType('file_manager.file_search_dialog')
    fake_dialog = MagicMock()
    fake_dialog.exec = MagicMock()
    # Dialog constructor returns an object with exec
    mod.FileSearchDialog = lambda parent=None: fake_dialog
    sys.modules['file_manager.file_search_dialog'] = mod

    widget = FileManagerWidget()
    # click toolbar search button
    widget.search_button.click()

    # ensure exec() was called on our fake dialog
    fake_dialog.exec.assert_called_once()

    # cleanup
    del sys.modules['file_manager.file_search_dialog']

def test_attribute_column_uses_default_background(qtbot, tmp_path):
    """属性列の背景色が交互色に干渉しないことを確認"""
    sample_file = tmp_path / 'sample.txt'
    sample_file.write_text('dummy')
    model = CustomFileSystemModel()
    model.setRootPath(str(tmp_path))
    root_index = model.index(str(tmp_path))
    qtbot.waitUntil(lambda: model.rowCount(root_index) >= 1, timeout=2000)
    item_index = model.index(str(sample_file))
    assert item_index.isValid()
    attr_index = model.index(item_index.row(), 6, item_index.parent())
    assert attr_index.isValid()
    assert model.data(attr_index, Qt.BackgroundRole) is None

