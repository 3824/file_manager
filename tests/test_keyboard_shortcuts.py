"""キーボードショートカットのテスト"""
import os
import sys

from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import file_manager.file_manager as fm


@pytest.fixture
def make_widget(qtbot):
    def _make(tmp_path):
        widget = fm.FileManagerWidget()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_current_path(str(tmp_path))
        qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)
        return widget

    return _make


def _select_path(widget, path):
    """指定ファイル/フォルダをリストで選択する"""
    source_index = widget.file_system_model.index(str(path))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )
    widget.list_view.setCurrentIndex(proxy_index)


def test_delete_key_calls_move_to_trash(monkeypatch, make_widget, qtbot, tmp_path):
    """Delete キーは move_selected_files_to_trash を呼ぶ（完全削除ではない）"""
    file_a = tmp_path / "a.txt"
    file_a.write_text("a", encoding="utf-8")
    widget = make_widget(tmp_path)
    _select_path(widget, file_a)

    called = {"trash": False, "delete": False}

    def fake_trash(self):
        called["trash"] = True

    def fake_delete(self):
        called["delete"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "move_selected_files_to_trash", fake_trash)
    monkeypatch.setattr(fm.FileManagerWidget, "delete_selected_files", fake_delete)

    widget.list_view.setFocus()
    QTest.keyClick(widget.list_view, Qt.Key.Key_Delete)

    assert called["trash"] is True
    assert called["delete"] is False


def test_shift_delete_key_calls_permanent_delete(monkeypatch, make_widget, qtbot, tmp_path):
    """Shift+Delete は完全削除を呼ぶ"""
    file_a = tmp_path / "a.txt"
    file_a.write_text("a", encoding="utf-8")
    widget = make_widget(tmp_path)
    _select_path(widget, file_a)

    called = {"trash": False, "delete": False}

    monkeypatch.setattr(fm.FileManagerWidget, "move_selected_files_to_trash",
                        lambda self: called.update(trash=True))
    monkeypatch.setattr(fm.FileManagerWidget, "delete_selected_files",
                        lambda self: called.update(delete=True))

    widget.list_view.setFocus()
    QTest.keyClick(widget.list_view, Qt.Key.Key_Delete, Qt.KeyboardModifier.ShiftModifier)

    assert called["delete"] is True
    assert called["trash"] is False


def test_f2_key_calls_rename(monkeypatch, make_widget, qtbot, tmp_path):
    """F2 はリネームを呼ぶ"""
    file_a = tmp_path / "a.txt"
    file_a.write_text("a", encoding="utf-8")
    widget = make_widget(tmp_path)
    _select_path(widget, file_a)

    called = {"renamed": False}
    monkeypatch.setattr(fm.FileManagerWidget, "rename_selected_file",
                        lambda self: called.update(renamed=True))

    widget.list_view.setFocus()
    QTest.keyClick(widget.list_view, Qt.Key.Key_F2)

    assert called["renamed"] is True


def test_f5_key_calls_refresh(monkeypatch, make_widget, qtbot, tmp_path):
    """F5 は表示更新を呼ぶ"""
    widget = make_widget(tmp_path)

    called = {"refreshed": False}
    monkeypatch.setattr(fm.FileManagerWidget, "refresh",
                        lambda self: called.update(refreshed=True))

    widget.setFocus()
    QTest.keyClick(widget, Qt.Key.Key_F5)

    assert called["refreshed"] is True


def test_alt_up_navigates_to_parent(make_widget, qtbot, tmp_path):
    """Alt+Up は親フォルダへ移動する"""
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(child)

    widget.setFocus()
    QTest.keyClick(widget, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    assert Path(widget.current_path).resolve() == tmp_path.resolve()


def test_backspace_in_list_navigates_up(make_widget, qtbot, tmp_path):
    """list_view 上で Backspace を押すと親フォルダへ"""
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(child)

    widget.list_view.setFocus()
    QTest.keyClick(widget.list_view, Qt.Key.Key_Backspace)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    assert Path(widget.current_path).resolve() == tmp_path.resolve()


def test_ctrl_l_focuses_address_bar(make_widget, qtbot, tmp_path):
    """Ctrl+L はアドレスバーにフォーカスを移す"""
    widget = make_widget(tmp_path)
    widget.setFocus()

    QTest.keyClick(widget, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)

    assert widget.address_bar.hasFocus()


def test_open_selected_video_player_uses_selected_video(monkeypatch, make_widget, qtbot, tmp_path):
    """選択動画を別ウィンドウプレーヤーへ渡す"""
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"dummy")
    calls = []

    class FakeVideoPlayerWindow:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def load_video(self, path, *, autoplay=True):
            calls.append((path, autoplay))

        def close(self):
            pass

    monkeypatch.setattr(fm, "VIDEO_PLAYER_AVAILABLE", True)
    monkeypatch.setattr(fm, "VideoPlayerWindow", FakeVideoPlayerWindow)

    widget = make_widget(tmp_path)
    widget.video_player_enabled = True
    monkeypatch.setattr(widget, "_get_selected_video_path", lambda: str(video))

    widget.open_selected_video_player()

    assert len(calls) == 1
    assert Path(calls[0][0]).resolve() == video.resolve()
    assert calls[0][1] is True


def test_ctrl_h_toggles_hidden_files(monkeypatch, make_widget, qtbot, tmp_path):
    """Ctrl+H で隠しファイル表示が切り替わる"""
    widget = make_widget(tmp_path)
    initial = widget.show_hidden

    widget.setFocus()
    QTest.keyClick(widget, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)

    assert widget.show_hidden != initial


def test_ctrl_shift_n_creates_new_folder(monkeypatch, make_widget, qtbot, tmp_path):
    """Ctrl+Shift+N で新規フォルダ作成が呼ばれる"""
    widget = make_widget(tmp_path)

    called = {"new": False}
    monkeypatch.setattr(fm.FileManagerWidget, "create_new_folder",
                        lambda self: called.update(new=True))

    widget.setFocus()
    QTest.keyClick(
        widget, Qt.Key.Key_N,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert called["new"] is True


def test_delete_key_does_not_fire_in_address_bar(monkeypatch, make_widget, qtbot, tmp_path):
    """アドレスバー編集中の Delete キーはファイル削除を発火しない（誤操作防止）"""
    file_a = tmp_path / "a.txt"
    file_a.write_text("a", encoding="utf-8")
    widget = make_widget(tmp_path)
    _select_path(widget, file_a)

    called = {"trash": False}
    monkeypatch.setattr(fm.FileManagerWidget, "move_selected_files_to_trash",
                        lambda self: called.update(trash=True))

    # アドレスバーにフォーカスを当てる
    widget.address_bar.setFocus()
    QTest.keyClick(widget.address_bar, Qt.Key.Key_Delete)

    assert called["trash"] is False
