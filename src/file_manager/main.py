#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application entry point for the GUI file manager."""

import os
import shutil
import sys

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget, QVBoxLayout


class _ClickEventFilter(QObject):
    """QLabel などの mousePressEvent を event filter 経由でフックする。"""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            self._callback(event)
            return True
        return super().eventFilter(obj, event)

from .file_manager import FileManagerWidget
from .ui_theme import apply_theme, try_enable_mica, _is_mica_capable

# 開発モード: 環境変数 FILE_MANAGER_DEV_TOOLS=1 または --dev 引数で有効化
# 注: pytest --debug と衝突しないよう独自フラグ名を使用する
_DEV_MODE = bool(os.environ.get("FILE_MANAGER_DEV_TOOLS")) or "--dev" in sys.argv
if _DEV_MODE:
    from .test_runner_dialog import TestRunnerDialog


def _format_capacity(byte_count: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(max(0, byte_count))
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024


def _drive_capacity_text(path: str) -> str:
    if not path:
        return ""
    try:
        target = path if os.path.exists(path) else os.path.dirname(path)
        if not target:
            return ""
        usage = shutil.disk_usage(target)
    except OSError:
        return ""
    return f"総容量: {_format_capacity(usage.total)} / 空き: {_format_capacity(usage.free)}"

# 旧テーマ定義（後方互換用に残す / テーマ移行後に削除予定）
_DARK_THEME_QSS = """
/* ===== Base ===== */
QWidget {
    background-color: #0F0F0F;
    color: #E8E8E8;
    font-family: "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
}

/* ===== MainWindow ===== */
QMainWindow {
    background-color: #0F0F0F;
}
QMainWindow::separator {
    background-color: #252525;
    width: 1px;
    height: 1px;
}

/* ===== MenuBar ===== */
QMenuBar {
    background-color: #141414;
    color: #D0D0D0;
    border-bottom: 1px solid #222222;
    padding: 2px 6px;
    spacing: 2px;
}
QMenuBar::item {
    background-color: transparent;
    padding: 5px 12px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: #6200EE;
    color: #FFFFFF;
}

/* ===== Menu ===== */
QMenu {
    background-color: #1C1C1C;
    color: #E0E0E0;
    border: 1px solid #303030;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px 7px 16px;
    border-radius: 6px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: #6200EE;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background-color: #2E2E2E;
    margin: 5px 8px;
}

/* ===== ToolBar ===== */
QToolBar {
    background-color: #141414;
    border-bottom: 1px solid #222222;
    spacing: 2px;
    padding: 4px 8px;
}
QToolBar::separator {
    width: 1px;
    background-color: #2E2E2E;
    margin: 4px 4px;
}
QToolBar QPushButton {
    background-color: transparent;
    color: #CCCCCC;
    border: none;
    border-radius: 7px;
    padding: 5px 9px;
    font-size: 16px;
    min-width: 32px;
    min-height: 32px;
}
QToolBar QPushButton:hover {
    background-color: #282828;
    color: #FFFFFF;
}
QToolBar QPushButton:pressed {
    background-color: #4A148C;
    color: #FFFFFF;
}
QToolBar QPushButton:checked {
    background-color: #6200EE;
    color: #FFFFFF;
}
QToolBar QPushButton:disabled {
    color: #3A3A3A;
}
QToolBar QComboBox {
    background-color: #1E1E1E;
    color: #D0D0D0;
    border: 1px solid #2E2E2E;
    border-radius: 7px;
    padding: 3px 10px;
    min-height: 30px;
}
QToolBar QComboBox:hover {
    border-color: #6200EE;
    background-color: #242424;
}
QToolBar QComboBox::drop-down {
    border: none;
    width: 18px;
}
QToolBar QLineEdit {
    background-color: #1E1E1E;
    color: #D0D0D0;
    border: 1px solid #2E2E2E;
    border-radius: 7px;
    padding: 3px 10px;
    min-height: 30px;
}
QToolBar QLineEdit:focus {
    border-color: #6200EE;
    background-color: #1A1A1A;
}

/* ===== Navigation bar (address bar row) ===== */
#navBar {
    background-color: #0F0F0F;
    border-bottom: 1px solid #1E1E1E;
}
#navBtn {
    background-color: transparent;
    color: #888888;
    border: none;
    border-radius: 6px;
    font-size: 18px;
    font-weight: 400;
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
    padding: 0;
}
#navBtn:hover {
    background-color: #242424;
    color: #E0E0E0;
}
#navBtn:pressed {
    background-color: #6200EE;
    color: #FFFFFF;
}
#navBtn:disabled {
    color: #333333;
}
#addressBar {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 13px;
    min-height: 30px;
    selection-background-color: #6200EE;
}
#addressBar:focus {
    border-color: #6200EE;
    background-color: #161616;
}
#addressBar:hover {
    border-color: #3D3D3D;
}

/* ===== Drive bar ===== */
#driveBar {
    background-color: #141414;
    border-bottom: 1px solid #1E1E1E;
}
#driveBar QLabel {
    color: #555555;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}
#driveBar QPushButton {
    background-color: #1E1E1E;
    color: #BBBBBB;
    border: 1px solid #2E2E2E;
    border-radius: 14px;
    padding: 2px 12px;
    min-width: 32px;
    min-height: 26px;
    font-size: 12px;
    font-weight: 700;
}
#driveBar QPushButton:hover {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border-color: #444444;
}
#driveBar QPushButton:checked {
    background-color: #6200EE;
    color: #FFFFFF;
    border-color: #7C4DFF;
}

/* ===== Left pane tree panel ===== */
#treePanel {
    background-color: #111111;
    border-right: 1px solid #1E1E1E;
}
#treePanel QLabel {
    color: #444444;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 2px 0;
    background: transparent;
}

/* ===== TreeView ===== */
QTreeView {
    background-color: #111111;
    border: none;
    color: #D8D8D8;
    alternate-background-color: #141414;
    selection-background-color: #6200EE;
    selection-color: #FFFFFF;
    outline: none;
    show-decoration-selected: 1;
}
QTreeView::item {
    padding: 4px 6px;
    border-radius: 5px;
    min-height: 24px;
}
QTreeView::item:hover {
    background-color: #1E1E1E;
}
QTreeView::item:selected {
    background-color: #6200EE;
    color: #FFFFFF;
}
QTreeView::item:selected:!active {
    background-color: #3700B3;
    color: #C8C8C8;
}
QTreeView::branch {
    background: transparent;
}
QTreeView::branch:hover {
    background-color: #1E1E1E;
}

/* ===== File list view (right pane) ===== */
QTreeView#fileList {
    background-color: #0F0F0F;
    alternate-background-color: #131313;
    color: #E0E0E0;
    border: none;
    outline: none;
    selection-background-color: #6200EE;
    selection-color: #FFFFFF;
    show-decoration-selected: 1;
}
QTreeView#fileList::item {
    padding: 5px 6px;
    min-height: 24px;
}
QTreeView#fileList::item:hover {
    background-color: #1A1A1A;
}
QTreeView#fileList::item:selected {
    background-color: #6200EE;
    color: #FFFFFF;
}
QTreeView#fileList::item:selected:!active {
    background-color: #3700B3;
    color: #C8C8C8;
}

/* ===== HeaderView ===== */
QHeaderView {
    background-color: #0F0F0F;
    border: none;
}
QHeaderView::section {
    background-color: #141414;
    color: #666666;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid #222222;
    border-bottom: 1px solid #222222;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
QHeaderView::section:hover {
    background-color: #1E1E1E;
    color: #E0E0E0;
}
QHeaderView::section:first {
    border-left: none;
}

/* ===== ScrollBar ===== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: #2A2A2A;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #6200EE;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0 2px;
}
QScrollBar::handle:horizontal {
    background: #2A2A2A;
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #6200EE;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ===== Splitter ===== */
QSplitter {
    background: transparent;
}
QSplitter::handle:horizontal {
    background-color: #1E1E1E;
    width: 2px;
}
QSplitter::handle:horizontal:hover {
    background-color: #6200EE;
}

/* ===== ProgressBar ===== */
QProgressBar {
    background-color: #1A1A1A;
    border: none;
    border-radius: 2px;
    text-align: center;
    color: transparent;
    max-height: 3px;
}
QProgressBar::chunk {
    background-color: #7C4DFF;
    border-radius: 2px;
}

/* ===== General QPushButton ===== */
QPushButton {
    background-color: #1E1E1E;
    color: #D8D8D8;
    border: 1px solid #2E2E2E;
    border-radius: 8px;
    padding: 7px 18px;
    font-size: 13px;
    min-height: 32px;
}
QPushButton:hover {
    background-color: #282828;
    border-color: #3D3D3D;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #6200EE;
    border-color: #6200EE;
    color: #FFFFFF;
}
QPushButton:checked {
    background-color: #6200EE;
    border-color: #7C4DFF;
    color: #FFFFFF;
}
QPushButton:disabled {
    color: #3A3A3A;
    background-color: #141414;
    border-color: #1E1E1E;
}
QPushButton:default {
    background-color: #6200EE;
    border-color: #7C4DFF;
    color: #FFFFFF;
}
QPushButton:default:hover {
    background-color: #7C4DFF;
}

/* ===== ComboBox ===== */
QComboBox {
    background-color: #1E1E1E;
    color: #D8D8D8;
    border: 1px solid #2E2E2E;
    border-radius: 8px;
    padding: 5px 12px;
    min-height: 32px;
}
QComboBox:hover {
    border-color: #6200EE;
    background-color: #222222;
}
QComboBox:focus {
    border-color: #6200EE;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: #1C1C1C;
    color: #E0E0E0;
    border: 1px solid #303030;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #6200EE;
    selection-color: #FFFFFF;
    outline: none;
}

/* ===== LineEdit ===== */
QLineEdit {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 32px;
    selection-background-color: #6200EE;
}
QLineEdit:focus {
    border-color: #6200EE;
    background-color: #161616;
}
QLineEdit:hover {
    border-color: #3D3D3D;
}
QLineEdit:disabled {
    color: #3A3A3A;
    background-color: #141414;
}

/* ===== SpinBox ===== */
QSpinBox, QDoubleSpinBox {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 5px 10px;
    min-height: 32px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #6200EE;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #252525;
    border: none;
    border-radius: 4px;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #6200EE;
}

/* ===== FontComboBox ===== */
QFontComboBox {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 5px 10px;
    min-height: 32px;
}
QFontComboBox:hover {
    border-color: #6200EE;
}

/* ===== CheckBox ===== */
QCheckBox {
    color: #D8D8D8;
    spacing: 8px;
    font-size: 13px;
}

/* ===== RadioButton ===== */
QRadioButton {
    color: #D8D8D8;
    spacing: 8px;
    font-size: 13px;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid #3A3A3A;
    background-color: #1A1A1A;
}
QRadioButton::indicator:hover {
    border-color: #7C4DFF;
}
QRadioButton::indicator:checked {
    background-color: #6200EE;
    border-color: #7C4DFF;
}

/* ===== Label ===== */
QLabel {
    color: #909090;
    font-size: 13px;
    background: transparent;
}

/* ===== GroupBox ===== */
QGroupBox {
    color: #909090;
    border: 1px solid #222222;
    border-radius: 10px;
    margin-top: 16px;
    padding-top: 12px;
    padding-bottom: 8px;
    font-size: 12px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 0px;
    color: #666666;
    background-color: #0F0F0F;
    padding: 0 6px;
}

/* ===== TabWidget ===== */
QTabWidget::pane {
    border: 1px solid #222222;
    border-radius: 0 10px 10px 10px;
    background-color: #141414;
    top: -1px;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background-color: #1A1A1A;
    color: #777777;
    padding: 8px 20px;
    border-radius: 7px 7px 0 0;
    border: 1px solid #222222;
    border-bottom: none;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #141414;
    color: #FFFFFF;
    border-color: #222222;
    border-bottom-color: #141414;
}
QTabBar::tab:hover:!selected {
    color: #D8D8D8;
    background-color: #1E1E1E;
}

/* ===== Dialog ===== */
QDialog {
    background-color: #141414;
}

/* ===== ListWidget ===== */
QListWidget {
    background-color: #141414;
    border: 1px solid #222222;
    border-radius: 10px;
    color: #E0E0E0;
    alternate-background-color: #181818;
    outline: none;
}
QListWidget::item {
    padding: 7px 10px;
    border-radius: 5px;
    margin: 1px 4px;
    min-height: 22px;
}
QListWidget::item:hover {
    background-color: #1E1E1E;
}
QListWidget::item:selected {
    background-color: #6200EE;
    color: #FFFFFF;
}

/* ===== StatusBar ===== */
QStatusBar {
    background-color: #141414;
    color: #555555;
    border-top: 1px solid #1E1E1E;
    font-size: 11px;
    padding: 2px 10px;
}
QStatusBar::item {
    border: none;
}
#statusPathLabel {
    color: #555555;
    font-size: 11px;
    background: transparent;
}

/* ===== ToolTip ===== */
QToolTip {
    background-color: #252525;
    color: #E0E0E0;
    border: 1px solid #3D3D3D;
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 12px;
}

/* ===== Frame ===== */
QFrame {
    background-color: transparent;
    border: none;
}
"""


_CLASSIC_THEME_QSS = """
QWidget {
    background-color: #F0F0F0;
    color: #000000;
    font-family: "MS UI Gothic", "Yu Gothic UI", "Meiryo", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #F0F0F0;
}
QMainWindow::separator {
    background-color: #C8C8C8;
    width: 4px;
    height: 4px;
}

QMenuBar {
    background-color: #F0F0F0;
    color: #000000;
    border-bottom: 1px solid #C8C8C8;
    padding: 1px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: #DCEBFF;
    color: #000000;
}
QMenu {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #8A8A8A;
    padding: 2px;
}
QMenu::item {
    padding: 4px 26px 4px 18px;
}
QMenu::item:selected {
    background-color: #0A64D8;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background-color: #C8C8C8;
    margin: 4px 6px;
}

QToolBar {
    background-color: #ECE9D8;
    border-top: 1px solid #FFFFFF;
    border-bottom: 1px solid #ACA899;
    spacing: 2px;
    padding: 3px 4px;
}
QToolBar::separator {
    width: 1px;
    background-color: #ACA899;
    margin: 2px 5px;
}
QToolBar QPushButton {
    background-color: transparent;
    color: #000000;
    border: 1px solid transparent;
    border-radius: 0;
    padding: 2px 6px;
    min-width: 26px;
    min-height: 24px;
    font-size: 15px;
}
QToolBar QPushButton:hover {
    background-color: #FFF7D7;
    border-color: #316AC5;
}
QToolBar QPushButton:pressed, QToolBar QPushButton:checked {
    background-color: #C1D2EE;
    border-color: #316AC5;
}
QToolBar QPushButton:disabled {
    color: #808080;
}
QToolBar QComboBox, QToolBar QLineEdit {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #7F9DB9;
    border-radius: 0;
    padding: 2px 5px;
    min-height: 22px;
}

#driveBar {
    background-color: #ECE9D8;
    border-top: 1px solid #FFFFFF;
    border-bottom: 1px solid #ACA899;
}
#driveBar QLabel {
    color: #333333;
    font-weight: 700;
    font-size: 12px;
}
#driveBar QPushButton {
    background-color: #F0F0F0;
    color: #000000;
    border: 1px solid #ACA899;
    border-radius: 0;
    padding: 1px 10px;
    min-width: 34px;
    min-height: 22px;
    font-weight: 700;
}
#driveBar QPushButton:hover {
    background-color: #FFF7D7;
    border-color: #316AC5;
}
#driveBar QPushButton:checked {
    background-color: #FFFFFF;
    border-color: #316AC5;
}

#navBar {
    background-color: #ECE9D8;
    border-bottom: 1px solid #ACA899;
}
#navBtn {
    background-color: #F0F0F0;
    color: #000000;
    border: 1px solid #ACA899;
    border-radius: 0;
    padding: 0;
}
#navBtn:hover {
    background-color: #FFF7D7;
    border-color: #316AC5;
}
#navBtn:disabled {
    color: #808080;
}
#addressBar {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #7F9DB9;
    border-radius: 0;
    padding: 3px 7px;
    selection-background-color: #0A64D8;
    selection-color: #FFFFFF;
}

#treePanel {
    background-color: #FFFFFF;
    border-right: 1px solid #ACA899;
}
#treePanel QLabel {
    background-color: #ECE9D8;
    color: #333333;
    border-bottom: 1px solid #D8D2BD;
    font-size: 11px;
    font-weight: 700;
}

QTreeView {
    background-color: #FFFFFF;
    alternate-background-color: #F7FBFF;
    color: #000000;
    border: 1px solid #D4D0C8;
    selection-background-color: #0A64D8;
    selection-color: #FFFFFF;
    outline: none;
    show-decoration-selected: 1;
}
QTreeView::item {
    padding: 2px 4px;
    min-height: 22px;
}
QTreeView::item:hover {
    background-color: #EAF3FF;
}
QTreeView::item:selected {
    background-color: #0A64D8;
    color: #FFFFFF;
}

QTreeView#fileList {
    background-color: #FFFFFF;
    alternate-background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #D4D0C8;
    selection-background-color: #0A64D8;
    selection-color: #FFFFFF;
}
QTreeView#fileList::item {
    padding: 4px 5px;
    min-height: 28px;
}

QHeaderView::section {
    background-color: #ECE9D8;
    color: #000000;
    padding: 4px 8px;
    border: 1px solid #ACA899;
    border-left-color: #FFFFFF;
    border-top-color: #FFFFFF;
}

QSplitter::handle:horizontal {
    background-color: #D4D0C8;
    width: 6px;
}
QProgressBar {
    background-color: #FFFFFF;
    border: 1px solid #7F9DB9;
    border-radius: 0;
    color: #000000;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #0A64D8;
}

QPushButton {
    background-color: #F0F0F0;
    color: #000000;
    border: 1px solid #ACA899;
    border-radius: 0;
    padding: 4px 14px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #FFF7D7;
    border-color: #316AC5;
}
QPushButton:pressed, QPushButton:checked {
    background-color: #C1D2EE;
    border-color: #316AC5;
}
QPushButton:disabled {
    color: #808080;
    background-color: #E5E5E5;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #7F9DB9;
    border-radius: 0;
    padding: 3px 6px;
    min-height: 23px;
    selection-background-color: #0A64D8;
    selection-color: #FFFFFF;
}
QComboBox QAbstractItemView, QListWidget, QTableWidget {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #7F9DB9;
    selection-background-color: #0A64D8;
    selection-color: #FFFFFF;
}

QCheckBox, QRadioButton, QLabel, QGroupBox {
    background: transparent;
    color: #000000;
}
QGroupBox {
    border: 1px solid #ACA899;
    margin-top: 12px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    background-color: #F0F0F0;
    padding: 0 4px;
}
QTabWidget::pane {
    background-color: #F0F0F0;
    border: 1px solid #ACA899;
}
QTabBar::tab {
    background-color: #ECE9D8;
    color: #000000;
    border: 1px solid #ACA899;
    padding: 5px 14px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    border-bottom-color: #FFFFFF;
}
QStatusBar {
    background-color: #ECE9D8;
    color: #000000;
    border-top: 1px solid #ACA899;
}
#statusPathLabel {
    color: #000000;
}
QToolTip {
    background-color: #FFFFE1;
    color: #000000;
    border: 1px solid #000000;
}
QFrame {
    background-color: transparent;
    border: none;
}
"""


class MainWindow(QMainWindow):
    """Main application window that hosts the FileManagerWidget."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ファイルマネージャ")

        # Mica を使うには show() より前に WA_TranslucentBackground を設定する必要がある
        self._mica_attempted = False
        if _is_mica_capable():
            self.setAttribute(Qt.WA_TranslucentBackground)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.file_manager = FileManagerWidget()
        layout.addWidget(self.file_manager)

        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_status_bar()

        self._restore_geometry()

    def _restore_geometry(self) -> None:
        settings = QSettings("FileManager", "Settings")
        geometry = settings.value("mainwindow/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.setGeometry(100, 100, 1280, 800)

    def _restore_toolbar_state(self) -> None:
        settings = QSettings("FileManager", "Settings")
        state = settings.value("mainwindow/toolbar_state")
        if state:
            self.restoreState(state)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._mica_attempted:
            return
        self._mica_attempted = True
        hwnd = int(self.winId())
        mica_ok = try_enable_mica(hwnd)
        app = QApplication.instance()
        if app is not None:
            if mica_ok:
                # Mica 有効: QMainWindow を透明にして Mica を透過させる
                apply_theme(app, mica_active=True)
            elif _is_mica_capable():
                # Mica 対応 OS だが DWM 呼び出しが失敗した場合は透過属性を解除して再描画
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                apply_theme(app)

    def closeEvent(self, event) -> None:
        settings = QSettings("FileManager", "Settings")
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        settings.setValue("mainwindow/toolbar_state", self.saveState())
        # 子ウィジェットの closeEvent は自動では呼ばれないため明示的に状態をフラッシュ
        try:
            if hasattr(self, 'file_manager') and hasattr(self.file_manager, 'save_window_state'):
                self.file_manager.save_window_state()
        except Exception:
            pass
        try:
            settings.sync()
        except Exception:
            pass
        super().closeEvent(event)

    def _setup_menu_bar(self) -> None:
        """Create top-level menus."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("ファイル(&F)")
        file_menu.addAction("終了(&X)", self.close)

        edit_menu = menubar.addMenu("編集(&E)")
        edit_menu.addAction("コピー(&C)", self.file_manager.copy_selected_files)
        edit_menu.addAction("切り取り(&X)", self.file_manager.cut_selected_files)
        edit_menu.addAction("貼り付け(&V)", self.file_manager.paste_files)
        edit_menu.addSeparator()
        edit_menu.addAction("削除(&D)", self.file_manager.delete_selected_files)
        edit_menu.addAction("名前変更(&R)", self.file_manager.rename_selected_file)

        view_menu = menubar.addMenu("表示(&V)")
        view_menu.addAction("更新(&R)", self.file_manager.refresh)
        view_menu.addSeparator()
        hidden_action = view_menu.addAction("隠しファイルを表示(&H)", self.file_manager.toggle_hidden_files)
        hidden_action.setCheckable(True)

        folder_menu = menubar.addMenu("フォルダ(&D)")
        folder_menu.addAction("新規フォルダ(&N)", self.file_manager.create_new_folder)
        folder_menu.addAction("上へ(&U)", self.file_manager.navigate_up)

        tools_menu = menubar.addMenu("ツール(&T)")
        tools_menu.addAction("ファイル検索(&S)", self.file_manager.show_file_search_dialog)
        tools_menu.addAction("ディスク分析(&D)", self.file_manager.show_disk_analysis_dialog)
        tools_menu.addAction("重複動画検出(&V)", self.file_manager.show_duplicate_videos_dialog)
        tools_menu.addAction("類似ファイル名検出(&F)", self.file_manager.show_filename_similarity_dialog)
        tools_menu.addAction("同サイズ検出(&Z)", self.file_manager.show_same_filesize_dialog)
        if _DEV_MODE:
            tools_menu.addSeparator()
            run_tests_action = tools_menu.addAction("テストを実行(&R)", self._open_test_runner)
            run_tests_action.setShortcut("Ctrl+Shift+T")

        options_menu = menubar.addMenu("オプション(&O)")
        options_menu.addAction("設定(&S)", self.file_manager.show_settings)

        menubar.addMenu("ヘルプ(&H)")

    def _open_test_runner(self) -> None:
        if _DEV_MODE:
            dialog = TestRunnerDialog(self)
            dialog.exec()

    def _setup_tool_bar(self) -> None:
        """FileManagerWidgetが保持するツールバーをフローティング対応でMainWindowに登録する。"""
        if not hasattr(self.file_manager, 'toolbar') or self.file_manager.toolbar is None:
            return
        toolbar = self.file_manager.toolbar
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        self._restore_toolbar_state()

    def _setup_status_bar(self) -> None:
        """ステータスバーをセットアップし、パス変化・選択変化時に更新する。"""
        # パスラベル: クリックでクリップボードコピー
        self._status_path_label = QLabel("")
        self._status_path_label.setObjectName("statusPathLabel")
        self._status_path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_path_label.setToolTip("クリックでパスをコピー")
        # PySide6 では instance への mousePressEvent 代入は C++ 仮想ディスパッチを
        # バイパスできないため event filter を使う
        self._path_click_filter = _ClickEventFilter(self._on_status_path_clicked, self)
        self._status_path_label.installEventFilter(self._path_click_filter)

        # 選択情報ラベル（中央）
        self._status_selection_label = QLabel("")
        self._status_selection_label.setObjectName("statusSelectionLabel")

        # ドライブ空き容量ラベル（右端）
        self._status_drive_label = QLabel("")
        self._status_drive_label.setObjectName("statusDriveLabel")

        self.statusBar().addWidget(self._status_path_label, 1)
        self.statusBar().addPermanentWidget(self._status_selection_label, 0)
        self.statusBar().addPermanentWidget(self._status_drive_label, 0)
        self.statusBar().showMessage("")

        # パス変化をフック
        if hasattr(self.file_manager, 'set_current_path'):
            orig = self.file_manager.set_current_path
            def _patched(path, _orig=orig):
                _orig(path)
                self._on_path_changed(path)
            self.file_manager.set_current_path = _patched

        # 選択変化を接続: selectionModel() は setModel() ごとに再生成されるため
        # FileManagerWidget.selection_changed シグナルを使う（モデル入れ替えに強い）
        try:
            self.file_manager.selection_changed.connect(self._on_selection_changed_status)
        except Exception:
            pass

        current = getattr(self.file_manager, 'current_path', '')
        if current:
            self._on_path_changed(current)

    def _on_status_path_clicked(self, event) -> None:
        """パスラベルをクリックしたときクリップボードにコピーする。"""
        path = getattr(self.file_manager, 'current_path', '')
        if path:
            QGuiApplication.clipboard().setText(path)
            self.statusBar().showMessage("パスをコピーしました", 2000)

    def _on_path_changed(self, path: str) -> None:
        if hasattr(self, '_status_path_label'):
            self._status_path_label.setText(path)
        if hasattr(self, '_status_drive_label'):
            self._status_drive_label.setText(_drive_capacity_text(path))
        self._update_selection_status()

    def _on_selection_changed_status(self, selected=None, deselected=None) -> None:
        self._update_selection_status()

    def _update_selection_status(self) -> None:
        """選択件数・合計サイズをステータスバーに反映する。"""
        if not hasattr(self, '_status_selection_label'):
            return
        try:
            fm = self.file_manager
            proxy = fm.proxy_model
            fs_model = fm.file_system_model
            sel_indexes = fm.list_view.selectionModel().selectedRows(0)
            total_count = proxy.rowCount()

            if sel_indexes:
                sel_size = 0
                for idx in sel_indexes:
                    src = proxy.mapToSource(idx)
                    fi = fs_model.fileInfo(src)
                    if fi.isFile():
                        sel_size += fi.size()
                sel_text = _format_capacity(sel_size) if sel_size else "0 B"
                text = f"選択 {len(sel_indexes)} / {total_count} 件  |  {sel_text}"
            else:
                text = f"全 {total_count} 件"

            self._status_selection_label.setText(text)
        except Exception:
            pass


def main() -> None:
    """Run the Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("ファイルマネージャ")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("FileManager")
    app.setStyle("Fusion")

    # デフォルトフォント:
    #   ラテン文字: Segoe UI Variable Text (Windows 11 本文用光学体, 11-14px で最適)
    #   日本語    : Yu Gothic UI (クリーンな現代的ゴシック、小サイズ可読性が高い)
    # QSS で font-family を上書きするが、QFontMetrics などの
    # 内部計算はここで設定した論理フォントを基準にする。
    _ui_font = QFont("Yu Gothic UI", 10)
    _ui_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(_ui_font)

    apply_theme(app, mode="light")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
