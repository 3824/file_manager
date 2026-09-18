import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_manager import left_pane
from file_manager.left_pane import (
    LeftPaneWidget,
    _calculate_folder_size,
    _format_folder_size,
)
from file_manager.main import _drive_capacity_text, _format_capacity


class _FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeWorker:
    started_paths = []

    def __init__(self):
        self.size_calculated = _FakeSignal()
        self.finished = _FakeSignal()

    def start_for(self, path):
        self.started_paths.append(path)


class _FakeIndex:
    def isValid(self):
        return True


class _FakeFolderModel:
    def __init__(self, paths):
        self.paths = list(paths)

    def filePath(self, index):
        return self.paths.pop(0)


class _FakeTreeView:
    def update(self, index):
        pass


def test_folder_size_click_starts_independent_workers(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _FakeWorker.started_paths = []

    monkeypatch.setattr(left_pane, "FolderSizeWorker", _FakeWorker)

    widget = LeftPaneWidget.__new__(LeftPaneWidget)
    widget.folder_sizes = {}
    widget._size_workers = {}
    widget.folder_model = _FakeFolderModel([str(first), str(second)])
    widget.tree_view = _FakeTreeView()

    index = _FakeIndex()
    LeftPaneWidget._on_tree_item_clicked(widget, index)
    LeftPaneWidget._on_tree_item_clicked(widget, index)

    assert _FakeWorker.started_paths == [str(first), str(second)]
    assert set(widget._size_workers) == {str(first), str(second)}


def test_calculate_folder_size_sums_nested_files(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "root.bin").write_bytes(b"a" * 1024)
    (nested / "child.bin").write_bytes(b"b" * 2048)

    assert _calculate_folder_size(str(tmp_path)) == 3072


def test_format_folder_size_uses_readable_units():
    assert _format_folder_size(512) == "512 B"
    assert _format_folder_size(2 * 1024 ** 2) == "2.0 MB"
    assert _format_folder_size(3 * 1024 ** 3) == "3.0 GB"
    assert _format_folder_size(4 * 1024 ** 4) == "4.0 TB"


def test_drive_capacity_text_includes_total_and_free(tmp_path):
    text = _drive_capacity_text(str(tmp_path))

    assert "総容量:" in text
    assert "空き:" in text


def test_format_capacity_scales_units():
    assert _format_capacity(512) == "512 B"
    assert _format_capacity(1536) == "1.5 KB"
