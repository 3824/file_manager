import os
import stat
import sys

from pathlib import Path

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QDir,
    QEvent,
    QItemSelectionModel,
    QPoint,
    QRect,
    QSettings,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QDialog, QMainWindow, QPushButton

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import file_manager.file_manager as fm
from file_manager.views import FileItemDelegate


@pytest.fixture
def make_widget(qtbot):
    def _make(tmp_path):
        settings = QSettings("FileManager", "Settings")
        settings.clear()
        settings.sync()
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


def test_breadcrumb_segments_include_parent_paths():
    path = os.path.join("root", "child", "leaf")

    segments = fm.FileManagerWidget._breadcrumb_segments(path)

    assert segments == [
        ("root", "root"),
        ("child", os.path.join("root", "child")),
        ("leaf", os.path.join("root", "child", "leaf")),
    ]


def test_breadcrumb_click_moves_to_parent(make_widget, qtbot, tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(child)

    buttons = widget.breadcrumb_bar.findChildren(QPushButton, "breadcrumbSegment")
    parent_button = next(
        button for button in buttons
        if Path(button.toolTip()).resolve() == tmp_path.resolve()
    )

    parent_button.click()
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    assert Path(widget.current_path).resolve() == tmp_path.resolve()
    assert widget.address_stack.currentWidget() == widget.breadcrumb_bar


def test_focus_address_bar_switches_to_text_editor(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)

    widget.focus_address_bar()

    assert widget.address_stack.currentWidget() == widget.address_bar
    assert widget.address_bar.text() == str(tmp_path)


def test_left_pane_folder_tree_is_visible(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)

    assert widget.left_pane.isVisible()
    assert widget.left_pane.drive_frame.isVisible()
    assert widget.left_pane.tree_header.isVisible()
    assert widget.left_pane.tree_header.text() == "FOLDERS"
    assert widget.left_pane.tree_frame.isVisible()
    assert widget.left_pane.tree_view.isVisible()
    assert widget.left_pane.width() >= 200
    assert widget.left_pane.drive_frame.height() >= 30
    assert widget.left_pane.tree_header.height() >= 24
    assert widget.left_pane.tree_view.height() > 0
    assert widget.left_pane.tree_view.model() is widget.left_pane.folder_model
    assert widget.left_pane.drive_buttons

    root_index = widget.left_pane.tree_view.rootIndex()
    assert root_index.isValid()
    assert widget.left_pane.folder_model.rowCount(root_index) > 0

    qtbot.waitUntil(
        lambda: (
            widget.left_pane.tree_view.currentIndex().isValid()
            and Path(
                widget.left_pane.folder_model.filePath(
                    widget.left_pane.tree_view.currentIndex()
                )
            ).resolve()
            == tmp_path.resolve()
        ),
        timeout=5000,
    )
    current_index = widget.left_pane.tree_view.currentIndex()
    assert current_index.isValid()
    assert Path(widget.left_pane.folder_model.filePath(current_index)).resolve() == tmp_path.resolve()


def test_address_entry_returns_to_breadcrumb(make_widget, qtbot, tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(tmp_path)

    widget.focus_address_bar()
    widget.address_bar.setText(str(child))
    widget.navigate_to_address()
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    assert Path(widget.current_path).resolve() == child.resolve()
    assert widget.address_stack.currentWidget() == widget.breadcrumb_bar


def test_save_window_state_round_trips_splitter_and_header(monkeypatch, qtbot, tmp_path):
    """save_window_state がスプリッター位置とヘッダ状態を保存し、次回起動で復元する。"""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    settings = QSettings("FileManagerTests", "WindowStateRoundTrip")
    settings.clear()
    settings.sync()

    monkeypatch.setattr(
        fm.FileManagerWidget,
        "_create_settings",
        staticmethod(lambda: settings),
    )

    # 1回目: 起動 → スプリッターを動かす → カレントパスをセット → 状態保存
    widget1 = fm.FileManagerWidget()
    qtbot.addWidget(widget1)
    widget1.set_current_path(str(target_dir))
    qtbot.waitUntil(lambda: not widget1.right_progress_bar.isVisible(), timeout=5000)

    # スプリッターを変更
    widget1.splitter.setSizes([200, 800])
    saved_sizes = widget1.splitter.sizes()
    # ヘッダの幅を変更
    header1 = widget1.list_view.header()
    header1.resizeSection(0, 333)

    widget1.save_window_state()

    # 2回目: 新しい widget を起動して復元状態を確認
    widget2 = fm.FileManagerWidget()
    qtbot.addWidget(widget2)
    qtbot.waitUntil(lambda: not widget2.right_progress_bar.isVisible(), timeout=5000)

    # last_path が復元されている
    assert Path(widget2.current_path).resolve() == target_dir.resolve()

    # スプリッターサイズが復元されている
    sizes2 = widget2.splitter.sizes()
    assert sizes2 == saved_sizes, f"splitter sizes not restored: {sizes2} vs {saved_sizes}"

    # ヘッダのサイズが復元されている
    assert widget2.list_view.header().sectionSize(0) == 333


def test_refresh_preserves_left_tree_expansion(make_widget, qtbot, tmp_path):
    """refresh() で左ペインの展開状態が失われないことを確認する。"""
    parent_dir = tmp_path / "parent"
    sub_dir = parent_dir / "sub"
    grandchild_dir = sub_dir / "grand"
    grandchild_dir.mkdir(parents=True)

    widget = make_widget(tmp_path)

    folder_model = widget.left_pane.folder_model
    tree_view = widget.left_pane.tree_view

    # 親フォルダが見えるよう、tmp_path をルートに
    widget._trigger_tree_load_for_path(str(grandchild_dir))

    parent_index = folder_model.index(str(parent_dir))
    sub_index = folder_model.index(str(sub_dir))
    assert parent_index.isValid()
    assert sub_index.isValid()

    tree_view.expand(parent_index)
    tree_view.expand(sub_index)
    assert tree_view.isExpanded(parent_index)
    assert tree_view.isExpanded(sub_index)

    widget.refresh()
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    # 復元は最大8回 × 150ms 間隔の遅延リトライで進むためポーリングで待つ
    def _both_expanded():
        p = folder_model.index(str(parent_dir))
        s = folder_model.index(str(sub_dir))
        return p.isValid() and s.isValid() and tree_view.isExpanded(p) and tree_view.isExpanded(s)

    qtbot.waitUntil(_both_expanded, timeout=5000)

    parent_index_after = folder_model.index(str(parent_dir))
    sub_index_after = folder_model.index(str(sub_dir))
    assert tree_view.isExpanded(parent_index_after), "refresh 後に親フォルダの展開が失われた"
    assert tree_view.isExpanded(sub_index_after), "refresh 後にサブフォルダの展開が失われた"


def test_set_current_path_syncs_left_tree(make_widget, qtbot, tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    widget = make_widget(tmp_path)

    widget.set_current_path(str(child))
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    current_index = widget.left_pane.tree_view.currentIndex()
    current_tree_path = widget.left_pane.folder_model.filePath(current_index)

    assert Path(current_tree_path).resolve() == child.resolve()


def test_apply_tree_selection_does_not_scroll_visible_item():
    class FakeIndex:
        def __init__(self, parent=None):
            self._parent = parent

        def parent(self):
            return self._parent or InvalidIndex()

    class InvalidIndex:
        def isValid(self):
            return False

    class FakeViewport:
        def rect(self):
            return QRect(0, 0, 300, 400)

    class FakeTreeView:
        def __init__(self):
            self.scroll_calls = []

        def expand(self, _index):
            pass

        def setCurrentIndex(self, _index):
            pass

        def visualRect(self, _index):
            return QRect(0, 120, 300, 24)

        def viewport(self):
            return FakeViewport()

        def scrollTo(self, index, hint):
            self.scroll_calls.append((index, hint))

    class FakeSettings:
        def setValue(self, _key, _value):
            pass

    tree_view = FakeTreeView()
    widget = fm.FileManagerWidget.__new__(fm.FileManagerWidget)
    widget.left_pane = type("LeftPane", (), {"tree_view": tree_view})()
    widget.settings = FakeSettings()
    widget._syncing_left_pane = False

    widget._apply_tree_selection(FakeIndex(), "C:\\visible")

    assert tree_view.scroll_calls == []


def test_apply_tree_selection_ensures_hidden_item_is_visible():
    class FakeIndex:
        def parent(self):
            return InvalidIndex()

    class InvalidIndex:
        def isValid(self):
            return False

    class FakeViewport:
        def rect(self):
            return QRect(0, 0, 300, 400)

    class FakeTreeView:
        def __init__(self):
            self.scroll_calls = []

        def setCurrentIndex(self, _index):
            pass

        def visualRect(self, _index):
            return QRect(0, 500, 300, 24)

        def viewport(self):
            return FakeViewport()

        def scrollTo(self, index, hint):
            self.scroll_calls.append((index, hint))

    class FakeSettings:
        def setValue(self, _key, _value):
            pass

    tree_view = FakeTreeView()
    widget = fm.FileManagerWidget.__new__(fm.FileManagerWidget)
    widget.left_pane = type("LeftPane", (), {"tree_view": tree_view})()
    widget.settings = FakeSettings()
    widget._syncing_left_pane = False
    tree_index = FakeIndex()

    widget._apply_tree_selection(tree_index, "C:\\hidden")

    assert tree_view.scroll_calls == [
        (tree_index, QAbstractItemView.EnsureVisible),
    ]


def test_startup_restores_last_displayed_path(monkeypatch, qtbot, tmp_path):
    last_path = tmp_path / "last"
    left_path = tmp_path / "left"
    last_path.mkdir()
    left_path.mkdir()

    settings = QSettings("FileManagerTests", "RestoreLastDisplayedPath")
    settings.clear()
    settings.setValue("last_path", str(last_path))
    settings.setValue("last_left_path", str(left_path))
    settings.sync()

    monkeypatch.setattr(
        fm.FileManagerWidget,
        "_create_settings",
        staticmethod(lambda: settings),
    )

    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    assert Path(widget.current_path).resolve() == last_path.resolve()


def test_refresh_button_triggers_progress(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)
    widget.refresh_button.click()
    qtbot.waitUntil(lambda: widget.right_progress_bar.isVisible(), timeout=2000)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)


def test_foreign_filename_checkbox_filters_files(make_widget, qtbot, tmp_path):
    english_file = tmp_path / "meeting_notes.txt"
    japanese_file = tmp_path / "ぎじろく.txt"
    chinese_file = tmp_path / "会议记录.txt"
    kanji_japanese_file = tmp_path / "請求書.txt"
    numeric_file = tmp_path / "2026-05-06.txt"
    english_file.write_text("english", encoding="utf-8")
    japanese_file.write_text("japanese", encoding="utf-8")
    chinese_file.write_text("chinese", encoding="utf-8")
    kanji_japanese_file.write_text("kanji-japanese", encoding="utf-8")
    numeric_file.write_text("numeric", encoding="utf-8")
    widget = make_widget(tmp_path)

    widget.foreign_filename_checkbox.setChecked(True)
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)

    root_index = widget.list_view.rootIndex()
    visible_names = {
        widget.proxy_model.data(widget.proxy_model.index(row, 0, root_index))
        for row in range(widget.proxy_model.rowCount(root_index))
    }

    assert english_file.name in visible_names
    assert chinese_file.name in visible_names
    assert japanese_file.name not in visible_names
    assert kanji_japanese_file.name not in visible_names
    assert numeric_file.name not in visible_names


def test_foreign_filename_filter_combines_with_search(make_widget, qtbot, tmp_path):
    target_file = tmp_path / "meeting_notes.txt"
    other_file = tmp_path / "holiday_photo.txt"
    target_file.write_text("target", encoding="utf-8")
    other_file.write_text("other", encoding="utf-8")
    widget = make_widget(tmp_path)

    widget.search_box.setText("meeting")
    widget.foreign_filename_checkbox.setChecked(True)

    def _visible_names():
        root_index = widget.list_view.rootIndex()
        return [
            widget.proxy_model.data(widget.proxy_model.index(row, 0, root_index))
            for row in range(widget.proxy_model.rowCount(root_index))
        ]

    # 検索ボックスは 150ms デバウンス後にフィルタが適用されるため、その反映を待つ
    qtbot.waitUntil(lambda: _visible_names() == [target_file.name], timeout=2000)


def test_hidden_button_toggles_flag(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)
    initial = widget.show_hidden
    widget.hidden_button.click()
    qtbot.waitUntil(lambda: True, timeout=10)

    assert widget.show_hidden != initial
    assert widget.hidden_button.isChecked() == widget.show_hidden


def test_hidden_files_are_shown_by_default(make_widget, tmp_path):
    widget = make_widget(tmp_path)
    filters = widget.file_system_model.filter()

    assert widget.show_hidden is True
    assert widget.hidden_button.isChecked() is True
    assert bool(filters & QDir.Hidden)
    assert bool(filters & QDir.System)


def test_file_delegate_uses_configured_normal_color(make_widget, tmp_path):
    target_file = tmp_path / "normal.txt"
    target_file.write_text("normal", encoding="utf-8")
    widget = make_widget(tmp_path)
    widget.attribute_colors["normal"] = "#123456"
    delegate = FileItemDelegate(widget)
    file_info = widget.file_system_model.fileInfo(widget.file_system_model.index(str(target_file)))

    assert delegate.get_file_color(file_info) == "#123456"


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

    menu = widget._build_tree_context_menu(target_index)
    duplicate_action = next(
        action for action in menu.actions() if action.text() == "重複動画を検出"
    )
    duplicate_action.trigger()

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


def test_settings_apply_button_calls_persist_without_closing(monkeypatch, qtbot):
    """適用ボタンを押すと _persist_settings が呼ばれ、ダイアログは閉じないこと"""
    settings = QSettings("TestOrg", "TestApply")
    settings.clear()
    settings.sync()

    dialog = fm.SettingsDialog(None, settings, {"name": True, "size": True})
    qtbot.addWidget(dialog)
    dialog.show()

    persist_called = {}

    def fake_persist():
        persist_called["called"] = True

    monkeypatch.setattr(dialog, "_persist_settings", fake_persist)

    dialog.apply_button.click()

    assert persist_called.get("called") is True
    assert dialog.isVisible(), "適用ボタンを押してもダイアログは閉じない"


def test_settings_apply_button_shows_feedback(monkeypatch, qtbot):
    """適用ボタンを押すとフィードバックラベルにメッセージが表示されること"""
    settings = QSettings("TestOrg", "TestApplyFeedback")
    settings.clear()
    settings.sync()

    dialog = fm.SettingsDialog(None, settings, {"name": True})
    qtbot.addWidget(dialog)
    dialog.show()

    monkeypatch.setattr(dialog, "_persist_settings", lambda: None)

    dialog.apply_button.click()

    assert "適用しました" in dialog._apply_feedback_label.text()


def test_settings_apply_button_exists(qtbot):
    """設定ダイアログに apply_button が存在すること"""
    settings = QSettings("TestOrg", "TestApplyExists")
    dialog = fm.SettingsDialog(None, settings, {"name": True})
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "apply_button"), "設定ダイアログに apply_button がない"
    assert isinstance(dialog.apply_button, QPushButton)


def test_settings_apply_rebuilds_mainwindow_toolbar(make_widget, qtbot, tmp_path):
    """設定ダイアログの適用後も MainWindow 上のツールバーが表示されること"""
    widget = make_widget(tmp_path)
    window = QMainWindow()
    qtbot.addWidget(window)
    window.setCentralWidget(widget)
    window.addToolBar(Qt.TopToolBarArea, widget.toolbar)
    window.show()

    dialog = fm.SettingsDialog(widget, widget.settings, widget.visible_columns)
    qtbot.addWidget(dialog)
    dialog.show()

    for row in range(dialog.toolbar_list.count()):
        item = dialog.toolbar_list.item(row)
        if item.data(Qt.UserRole) == "up":
            item.setCheckState(Qt.Unchecked)
            break
    else:
        pytest.fail("toolbar settings list does not contain the up button")

    dialog.apply_button.click()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qtbot.waitUntil(lambda: True, timeout=10)

    toolbar_widgets = [
        widget.toolbar.widgetForAction(action)
        for action in widget.toolbar.actions()
        if widget.toolbar.widgetForAction(action) is not None
    ]

    assert toolbar_widgets
    assert widget.up_button not in toolbar_widgets
    assert widget.toolbar.isVisible()
    assert not widget.toolbar.isHidden()


def test_settings_dialog_reflects_saved_settings(qtbot):
    """設定画面を開いたとき、保存済みの設定値が各ウィジェットに反映されること"""
    settings = QSettings("TestOrg", "ReflectSettings")
    settings.clear()
    settings.setValue("video_thumbnail_count", 9)
    settings.setValue("ui/theme_mode", "dark")
    settings.setValue("video_digest_trigger", "middle")
    settings.sync()

    dialog = fm.SettingsDialog(None, settings, {"name": True, "size": False})
    qtbot.addWidget(dialog)

    assert dialog.thumbnail_count_spin.value() == 9
    assert dialog.theme_combo.currentData() == "dark"
    assert dialog.digest_trigger_combo.currentData() == "middle"
    assert dialog.size_checkbox.isChecked() is False


def test_settings_dialog_reflects_saved_colors(qtbot):
    """親が無い場合でも、保存済みの属性色が色設定タブに反映されること"""
    settings = QSettings("TestOrg", "ReflectColors")
    settings.clear()
    settings.setValue("color_hidden", "#123456")
    settings.setValue("color_readonly", "#ABCDEF")
    settings.sync()

    dialog = fm.SettingsDialog(None, settings, {"name": True})
    qtbot.addWidget(dialog)

    assert dialog.current_colors["hidden"] == "#123456"
    assert dialog.current_colors["readonly"] == "#ABCDEF"


def test_toolbar_widgets_visible_after_rebuild(make_widget, qtbot, tmp_path):
    """設定反映時の rebuild_toolbar 後もツールバーのウィジェットが消えないこと"""
    widget = make_widget(tmp_path)

    # 設定保存後に show_settings が行うのと同じ再構築を実行する
    widget.rebuild_toolbar()
    qtbot.waitUntil(lambda: True, timeout=10)

    toolbar_widgets = [
        widget.toolbar.widgetForAction(action)
        for action in widget.toolbar.actions()
        if widget.toolbar.widgetForAction(action) is not None
    ]

    assert toolbar_widgets, "ツールバーにウィジェットが存在しない"
    assert widget.toolbar.isVisible(), "rebuild_toolbar 後にツールバー本体が非表示になっている"


def test_toolbar_rebuild_falls_back_when_saved_order_is_invalid(make_widget, qtbot, tmp_path):
    widget = make_widget(tmp_path)
    widget.settings.setValue("toolbar_order", "[],unknown,SEP")
    widget.settings.sync()

    widget.rebuild_toolbar()
    qtbot.waitUntil(lambda: True, timeout=10)

    toolbar_widgets = [
        widget.toolbar.widgetForAction(action)
        for action in widget.toolbar.actions()
        if widget.toolbar.widgetForAction(action) is not None
    ]
    assert toolbar_widgets
    assert widget.toolbar.isVisible()


def test_settings_accept_keeps_mainwindow_toolbar_visible(monkeypatch, make_widget, qtbot, tmp_path):
    """設定保存フロー後も MainWindow 上のツールバー項目が残ること"""
    widget = make_widget(tmp_path)
    window = QMainWindow()
    qtbot.addWidget(window)
    window.setCentralWidget(widget)
    window.addToolBar(Qt.TopToolBarArea, widget.toolbar)
    window.show()

    original_dialog = fm.SettingsDialog

    class AutoAcceptSettingsDialog(original_dialog):
        def exec(self):
            self.accept()
            return QDialog.Accepted

    monkeypatch.setattr(fm, "SettingsDialog", AutoAcceptSettingsDialog)

    widget.show_settings()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qtbot.waitUntil(lambda: True, timeout=10)

    toolbar_widgets = [
        widget.toolbar.widgetForAction(action)
        for action in widget.toolbar.actions()
        if widget.toolbar.widgetForAction(action) is not None
    ]

    assert toolbar_widgets
    assert widget.toolbar.isVisible()
    assert not widget.toolbar.isHidden()


def test_settings_dialog_uses_saved_column_settings(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    settings.clear()
    settings.setValue("show_size", "false")
    settings.setValue("show_type", "false")
    settings.setValue("show_attributes", "true")
    settings.sync()

    dialog = fm.SettingsDialog(None, settings, {"name": True, "size": True, "type": True})
    qtbot.addWidget(dialog)

    assert dialog.size_checkbox.isChecked() is False
    assert dialog.type_checkbox.isChecked() is False
    assert dialog.attributes_checkbox.isChecked() is True


def test_list_context_menu_has_translate_action(monkeypatch, make_widget, tmp_path):
    target_file = tmp_path / "hello.txt"
    target_file.write_text("x", encoding="utf-8")
    widget = make_widget(tmp_path)

    source_index = widget.file_system_model.index(str(target_file))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    assert proxy_index.isValid()
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    monkeypatch.setattr(widget.list_view, "indexAt", lambda _pos: proxy_index)

    # _build_list_context_menu を直接呼び出してメニュー内容を検査する
    menu = widget._build_list_context_menu(proxy_index)
    action_texts = [action.text() for action in menu.actions() if not action.isSeparator()]

    assert "ファイル名を日本語に翻訳" in action_texts


def test_list_context_menu_has_attribute_actions(make_widget, tmp_path):
    target_file = tmp_path / "hello.txt"
    target_file.write_text("x", encoding="utf-8")
    widget = make_widget(tmp_path)

    source_index = widget.file_system_model.index(str(target_file))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    assert proxy_index.isValid()
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    menu = widget._build_list_context_menu(proxy_index)
    attr_action = next(
        action for action in menu.actions()
        if action.text() == "属性を変更"
    )
    attr_menu = attr_action.menu()

    assert attr_menu is not None
    assert attr_menu.isEnabled()
    assert [action.text() for action in attr_menu.actions()] == ["通常", "読み取り専用", "隠し"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-style attributes are tested off Windows")
def test_set_posix_file_attribute_readonly_hidden_and_normal(make_widget, tmp_path):
    target_file = tmp_path / "sample.txt"
    target_file.write_text("x", encoding="utf-8")
    widget = make_widget(tmp_path)

    widget._set_file_attribute(str(target_file), "readonly")
    assert not os.access(target_file, os.W_OK)

    os.chmod(target_file, os.stat(target_file).st_mode | stat.S_IWUSR)
    widget._set_file_attribute(str(target_file), "hidden")
    hidden_file = tmp_path / ".sample.txt"
    assert hidden_file.exists()

    widget._set_file_attribute(str(hidden_file), "normal")
    assert target_file.exists()
    assert os.access(target_file, os.W_OK)


def test_translate_selected_filenames_invokes_dialog(monkeypatch, make_widget, qtbot, tmp_path):
    target_file = tmp_path / "hello.txt"
    target_file.write_text("x", encoding="utf-8")
    widget = make_widget(tmp_path)

    source_index = widget.file_system_model.index(str(target_file))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    captured = {}

    class FakeTranslator:
        api_key = "dummy"
        requires_api_key = False

        @classmethod
        def from_env(cls):
            return cls()

    class FakeDialog:
        def __init__(self, parent, translator, paths):
            captured["paths"] = list(paths)

        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(fm, "FilenameTranslationService", FakeTranslator)
    monkeypatch.setattr(fm, "TranslatePreviewDialog", FakeDialog)

    widget.translate_selected_filenames()

    assert captured["paths"] == [target_file]


def test_translation_rename_does_not_overwrite_existing_file(tmp_path):
    source = tmp_path / "source.txt"
    target = tmp_path / "translated.txt"
    source.write_text("source", encoding="utf-8")
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        fm._rename_file_without_overwrite(source, target)

    assert source.read_text(encoding="utf-8") == "source"
    assert target.read_text(encoding="utf-8") == "existing"


def test_delete_selected_files_uses_highlight_selection(monkeypatch, make_widget, tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")
    widget = make_widget(tmp_path)

    source_index = widget.file_system_model.index(str(file_a))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    monkeypatch.setattr(fm, "silent_question", lambda *args, **kwargs: fm.QMessageBox.Yes)

    widget.delete_selected_files()

    assert not file_a.exists()
    assert file_b.exists()


def test_move_to_trash_uses_highlight_selection(monkeypatch, make_widget, tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")
    widget = make_widget(tmp_path)

    source_index = widget.file_system_model.index(str(file_b))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    captured = []
    monkeypatch.setattr(fm, "silent_question", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("confirm shown")))
    monkeypatch.setattr(fm, "silent_warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(widget, "move_to_trash", lambda path: captured.append(path) or True)

    widget.move_selected_files_to_trash()

    assert [Path(path).resolve() for path in captured] == [file_b.resolve()]


def test_delete_button_moves_selected_files_to_trash_without_confirm(monkeypatch, make_widget, tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_c = tmp_path / "c.txt"
    for path in (file_a, file_b, file_c):
        path.write_text(path.stem, encoding="utf-8")

    widget = make_widget(tmp_path)
    selection_model = widget.list_view.selectionModel()
    for path in (file_a, file_c):
        source_index = widget.file_system_model.index(str(path))
        assert source_index.isValid()
        proxy_index = widget.proxy_model.mapFromSource(source_index)
        selection_model.select(
            proxy_index,
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )

    captured = []
    monkeypatch.setattr(fm, "silent_question", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("confirm shown")))
    monkeypatch.setattr(fm, "silent_warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(widget, "move_to_trash", lambda path: captured.append(path) or True)

    widget.delete_button.click()

    assert {Path(path).resolve() for path in captured} == {file_a.resolve(), file_c.resolve()}
    assert widget._get_selected_paths() == []


def test_transfer_paths_to_directory_copy_and_move(make_widget, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    copy_file = source_dir / "copy.txt"
    move_file = source_dir / "move.txt"
    copy_file.write_text("copy", encoding="utf-8")
    move_file.write_text("move", encoding="utf-8")
    widget = make_widget(source_dir)

    copied, copy_errors = widget._transfer_paths_to_directory([str(copy_file)], str(target_dir), move=False)
    moved, move_errors = widget._transfer_paths_to_directory([str(move_file)], str(target_dir), move=True)

    assert copied == 1
    assert moved == 1
    assert copy_errors == []
    assert move_errors == []
    assert copy_file.exists()
    assert not move_file.exists()
    assert (target_dir / "copy.txt").exists()
    assert (target_dir / "move.txt").exists()


def test_overwrite_confirm_dialog_shows_source_and_existing_sizes(monkeypatch, make_widget, tmp_path):
    source_file = tmp_path / "source.txt"
    existing_file = tmp_path / "existing.txt"
    source_file.write_text("abc", encoding="utf-8")
    existing_file.write_text("existing", encoding="utf-8")
    widget = make_widget(tmp_path)

    captured = {}

    def fake_question(parent, title, message, buttons, default_button):
        captured["title"] = title
        captured["message"] = message
        return fm.QMessageBox.No

    monkeypatch.setattr(fm.QMessageBox, "question", fake_question)

    assert not widget._confirm_overwrite_destination(str(source_file), str(existing_file))
    assert captured["title"] == "上書き確認"
    assert "3 B" in captured["message"]
    assert "8 B" in captured["message"]


def test_transfer_paths_to_directory_cancel_overwrite_keeps_files(monkeypatch, make_widget, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_file = source_dir / "same.txt"
    target_file = target_dir / "same.txt"
    source_file.write_text("new", encoding="utf-8")
    target_file.write_text("old", encoding="utf-8")
    widget = make_widget(source_dir)

    monkeypatch.setattr(widget, "_confirm_overwrite_destination", lambda source, dest: False)

    copied, errors = widget._transfer_paths_to_directory(
        [str(source_file)],
        str(target_dir),
        move=False,
        confirm_overwrite=True,
    )

    assert copied == 0
    assert errors == []
    assert source_file.read_text(encoding="utf-8") == "new"
    assert target_file.read_text(encoding="utf-8") == "old"


def test_transfer_paths_to_directory_overwrites_existing_file(monkeypatch, make_widget, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    copy_file = source_dir / "copy.txt"
    move_file = source_dir / "move.txt"
    copy_target = target_dir / "copy.txt"
    move_target = target_dir / "move.txt"
    copy_file.write_text("new copy", encoding="utf-8")
    move_file.write_text("new move", encoding="utf-8")
    copy_target.write_text("old copy", encoding="utf-8")
    move_target.write_text("old move", encoding="utf-8")
    widget = make_widget(source_dir)

    monkeypatch.setattr(widget, "_confirm_overwrite_destination", lambda source, dest: True)

    copied, copy_errors = widget._transfer_paths_to_directory(
        [str(copy_file)],
        str(target_dir),
        move=False,
        confirm_overwrite=True,
    )
    moved, move_errors = widget._transfer_paths_to_directory(
        [str(move_file)],
        str(target_dir),
        move=True,
        confirm_overwrite=True,
    )

    assert copied == 1
    assert moved == 1
    assert copy_errors == []
    assert move_errors == []
    assert copy_file.exists()
    assert not move_file.exists()
    assert copy_target.read_text(encoding="utf-8") == "new copy"
    assert move_target.read_text(encoding="utf-8") == "new move"


def test_drop_to_folder_overwrites_after_confirmation(monkeypatch, make_widget, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_file = source_dir / "same.txt"
    target_file = target_dir / "same.txt"
    source_file.write_text("new", encoding="utf-8")
    target_file.write_text("old", encoding="utf-8")
    widget = make_widget(source_dir)

    monkeypatch.setattr(widget, "_prompt_drop_operation", lambda source, target: "copy")
    monkeypatch.setattr(widget, "_confirm_overwrite_destination", lambda source, dest: True)

    widget.on_files_dropped_to_folder([str(source_file)], str(target_dir))

    assert source_file.exists()
    assert target_file.read_text(encoding="utf-8") == "new"


def test_copy_and_paste_selected_file(make_widget, qtbot, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_file = source_dir / "copy.txt"
    source_file.write_text("copy", encoding="utf-8")
    widget = make_widget(source_dir)

    source_index = widget.file_system_model.index(str(source_file))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    widget.copy_selected_files()
    widget.set_current_path(str(target_dir))
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)
    widget.paste_files()

    assert source_file.exists()
    assert (target_dir / "copy.txt").read_text(encoding="utf-8") == "copy"


def test_cut_and_paste_selected_file_moves_file(make_widget, qtbot, tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_file = source_dir / "move.txt"
    source_file.write_text("move", encoding="utf-8")
    widget = make_widget(source_dir)

    source_index = widget.file_system_model.index(str(source_file))
    proxy_index = widget.proxy_model.mapFromSource(source_index)
    widget.list_view.selectionModel().select(
        proxy_index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )

    widget.cut_selected_files()
    widget.set_current_path(str(target_dir))
    qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)
    widget.paste_files()

    assert not source_file.exists()
    assert (target_dir / "move.txt").read_text(encoding="utf-8") == "move"
