import os
import sys

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog

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


def test_up_button_moves_to_parent(make_widget, qtbot, tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(child)

    widget.up_button.click()
    qtbot.waitUntil(lambda: True, timeout=10)

    assert widget.current_path == str(child.parent)


def test_refresh_button_triggers_progress(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)
    widget.refresh_button.click()
    qtbot.waitUntil(lambda: widget.right_progress_bar.isVisible(), timeout=2000)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)


def test_hidden_button_toggles_flag(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)
    initial = widget.show_hidden
    widget.hidden_button.click()
    qtbot.waitUntil(lambda: True, timeout=10)

    assert widget.show_hidden != initial
    assert widget.hidden_button.isChecked() == widget.show_hidden


def test_search_button_calls_handler(monkeypatch, qtbot):
    called = {}

    def fake_show(self):
        called["called"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "show_file_search_dialog", fake_show)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    widget.search_button.click()

    assert called.get("called") is True


def test_settings_button_calls_handler(monkeypatch, qtbot):
    called = {}

    def fake_show(self):
        called["called"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "show_settings", fake_show)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    widget.settings_button.click()

    assert called.get("called") is True


def test_disk_analysis_button_calls_handler(monkeypatch, qtbot):
    called = {}

    def fake_show(self):
        called["called"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "show_disk_analysis_dialog", fake_show)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    widget.disk_analysis_button.click()

    assert called.get("called") is True


def test_duplicate_videos_button_calls_handler(monkeypatch, qtbot):
    called = {}

    def fake_show(self):
        called["called"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "show_duplicate_videos_dialog", fake_show)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    assert widget.duplicate_videos_button.isEnabled()
    widget.duplicate_videos_button.click()

    assert called.get("called") is True


def test_move_to_trash_button_calls_handler(monkeypatch, qtbot):
    called = {}

    def fake_move(self):
        called["called"] = True

    monkeypatch.setattr(fm.FileManagerWidget, "move_selected_files_to_trash", fake_move)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    widget.move_to_trash_button.setEnabled(True)
    widget.move_to_trash_button.click()

    assert called.get("called") is True


def test_left_pane_drive_button_triggers_slot(monkeypatch, qtbot):
    monkeypatch.setattr(
        fm.LeftPaneWidget,
        "get_available_drives",
        lambda self: ["TEST"],
    )

    captured = {}

    def fake_on_drive(self, drive):
        captured["drive"] = drive

    monkeypatch.setattr(fm.LeftPaneWidget, "on_drive_selected", fake_on_drive)

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)

    drive_button = next(iter(widget.left_pane.drive_buttons.values()))
    drive_button.click()

    assert captured.get("drive") == "TEST"




def test_tree_context_menu_triggers_duplicate(monkeypatch, make_widget, qtbot, tmp_path):
    target_dir = tmp_path / "videos"
    target_dir.mkdir()
    widget = make_widget(tmp_path)

    captured = {}

    def fake_show(self, path=None):
        captured["path"] = path

    monkeypatch.setattr(fm.FileManagerWidget, "show_duplicate_videos_dialog", fake_show)

    model = widget.left_pane.folder_model
    target_index = model.index(str(target_dir))
    assert target_index.isValid()

    monkeypatch.setattr(widget.left_pane.tree_view, "indexAt", lambda _pos: target_index)

    def fake_exec(menu, _pos):
        non_sep_actions = [action for action in menu.actions() if not action.isSeparator()]
        captured["actions"] = [action.text() for action in non_sep_actions]
        if len(non_sep_actions) >= 3:
            non_sep_actions[2].trigger()
        elif non_sep_actions:
            non_sep_actions[-1].trigger()

    monkeypatch.setattr(fm.QMenu, "exec", fake_exec)

    widget.show_tree_context_menu(QPoint(0, 0))

    assert Path(captured.get("path")).resolve() == target_dir.resolve(), captured

def test_settings_color_button_updates_color(monkeypatch, qtbot):
    settings = QSettings("TestOrg", "TestApp")
    dialog = fm.SettingsDialog(None, settings, {"name": True, "size": True})
    qtbot.addWidget(dialog)

    monkeypatch.setattr(
        fm.QColorDialog,
        "getColor",
        lambda current, parent, title: QColor("#123456"),
    )

    dialog.hidden_color_button.click()

    assert dialog.current_colors["hidden"] == "#123456"


def test_settings_ok_and_cancel_buttons(monkeypatch, qtbot):
    settings = QSettings("TestOrg", "TestOk")
    dialog = fm.SettingsDialog(None, settings, {"name": True, "size": True})
    qtbot.addWidget(dialog)

    called = {}

    def fake_persist(self):
        called["persist"] = True

    monkeypatch.setattr(dialog, "_persist_settings", fake_persist.__get__(dialog, type(dialog)))
    monkeypatch.setattr(dialog, "_show_save_success_message", lambda: None)

    dialog.ok_button.click()

    assert called.get("persist") is True
    assert dialog.result() == QDialog.Accepted

    dialog2 = fm.SettingsDialog(None, settings, {"name": True, "size": True})
    qtbot.addWidget(dialog2)
    dialog2.cancel_button.click()

    assert dialog2.result() == QDialog.Rejected
