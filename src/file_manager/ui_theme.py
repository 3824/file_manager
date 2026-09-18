#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テーマトークンと QSS テンプレートエンジン。

外部から使う主な関数:
  apply_theme(app, mode)       ... アプリ全体にテーマを適用
  build_qss(tokens)            ... トークン辞書から QSS 文字列を生成
  get_saved_mode()             ... QSettings から保存済みモードを読み出す
  try_enable_mica(hwnd)        ... Windows 11 22H2+ で Mica を有効化
  get_system_accent_color()    ... Windows レジストリからアクセントカラーを取得
"""
from __future__ import annotations

import sys
from typing import Literal

ThemeMode = Literal["light", "dark", "system"]

# ── 共通トークン（ライト・ダーク 共通） ────────────────────────────────

_COMMON: dict[str, str] = {
    # 角丸
    "radius.xs":             "4px",
    "radius.sm":             "6px",
    "radius.md":             "8px",
    "radius.lg":             "8px",
    # タイポグラフィ
    # "Variable Text" 光学体: 本文サイズ (10-20px) 向けに最適化されており UI 用途に適切
    "font.family.ui": (
        '"Segoe UI Variable Text","Segoe UI","Yu Gothic UI","Meiryo",sans-serif'
    ),
    "font.family.mono":      '"Cascadia Code","Consolas",monospace',
    "font.size.xs":          "11px",
    "font.size.sm":          "12px",
    "font.size.md":          "13px",
    "font.size.lg":          "15px",
    "font.size.xl":          "18px",
    "font.weight.regular":   "400",
    "font.weight.medium":    "500",
    "font.weight.semibold":  "600",
    # サイズ
    "size.button.h":         "26px",
    "size.input.h":          "26px",
    "size.row.h":            "22px",
    "size.toolbar.h":        "36px",  # Phase 4: ツールバー高さ制御に使用予定
    "size.scrollbar.thin":   "4px",
    "size.scrollbar.thick":  "10px",
    "size.divider":          "1px",   # Phase 4: スプリッター幅制御に使用予定
    "size.drive.btn.h":      "28px",
    "size.folder.row.h":     "24px",
    "radius.pill":           "12px",
    "motion.hover.border":   "rgba(148,163,184,0.42)",
}

# ── ライトテーマ（Fluent / One Commander 風） ─────────────────────────

TOKENS_LIGHT: dict[str, str] = {
    **_COMMON,
    "bg.window":           "#E9EEF5",
    "bg.depth":            "#CBD5E1",
    "bg.surface":          "rgba(255,255,255,0.78)",
    "bg.subtle":           "rgba(248,250,252,0.66)",
    "bg.muted":            "rgba(226,232,240,0.82)",
    "bg.card":             "rgba(255,255,255,0.72)",
    "bg.card.hover":       "rgba(255,255,255,0.88)",
    "bg.sidebar":          "rgba(241,245,249,0.58)",
    "bg.hover":            "rgba(15,23,42,0.06)",
    "bg.pressed":          "rgba(15,23,42,0.11)",
    "border.subtle":       "rgba(148,163,184,0.28)",
    "border.strong":       "rgba(100,116,139,0.48)",
    "border.glass":        "rgba(255,255,255,0.60)",
    "text.primary":        "#0F172A",
    "text.secondary":      "#475569",
    "text.disabled":       "#94A3B8",
    "accent.primary":      "#38BDF8",
    "accent.hover":        "#0EA5E9",
    "accent.on":           "#FFFFFF",  # アクセント背景上のテキスト色
    "accent.bg.subtle":    "rgba(56,189,248,0.14)",
    "accent.selection.bg": "#DDF4FF",  # selection-background-color 用（不透明）
}

# ── ダークテーマ（Fluent Dark） ───────────────────────────────────────

TOKENS_DARK: dict[str, str] = {
    **_COMMON,
    "bg.window":           "#0F172A",  # Tailwind slate-900
    "bg.depth":            "#020617",
    "bg.surface":          "rgba(15,23,42,0.72)",
    "bg.subtle":           "rgba(30,41,59,0.56)",
    "bg.muted":            "rgba(51,65,85,0.70)",
    "bg.card":             "rgba(15,23,42,0.62)",
    "bg.card.hover":       "rgba(30,41,59,0.82)",
    "bg.sidebar":          "rgba(15,23,42,0.50)",
    "bg.hover":            "rgba(148,163,184,0.11)",
    "bg.pressed":          "rgba(148,163,184,0.18)",
    "border.subtle":       "rgba(148,163,184,0.18)",
    "border.strong":       "rgba(203,213,225,0.32)",
    "border.glass":        "rgba(255,255,255,0.12)",
    "text.primary":        "#F8FAFC",
    "text.secondary":      "#CBD5E1",
    "text.disabled":       "#64748B",
    "accent.primary":      "#67E8F9",
    "accent.hover":        "#22D3EE",
    "accent.on":           "#061828",  # アクセント背景上のテキスト色
    "accent.bg.subtle":    "rgba(103,232,249,0.14)",
    "accent.selection.bg": "#164E63",  # selection-background-color 用（不透明）
}

# ── QSS テンプレート ───────────────────────────────────────────────────
# {{token.key}} → build_qss() で tokens[key] に置換される

_QSS_TEMPLATE = """\
/* ===== Base ===== */
QWidget {
    background-color: {{bg.window}};
    color: {{text.primary}};
    font-family: {{font.family.ui}};
    font-size: {{font.size.md}};
}

/* ===== MainWindow ===== */
QMainWindow {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 {{bg.window}},
                                      stop:0.55 {{bg.surface}},
                                      stop:1 {{bg.depth}});
}
QMainWindow::separator {
    background-color: {{border.subtle}};
    width: 1px;
    height: 1px;
}

/* ===== MenuBar ===== */
QMenuBar {
    background-color: {{bg.surface}};
    color: {{text.primary}};
    border-bottom: 1px solid {{border.subtle}};
    padding: 1px 4px;
    spacing: 1px;
}
QMenuBar::item {
    background-color: transparent;
    padding: 4px 10px;
    border-radius: {{radius.sm}};
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: {{bg.hover}};
    color: {{text.primary}};
}

/* ===== Menu ===== */
QMenu {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    padding: 4px;
}
QMenu::item {
    padding: 5px 28px 5px 12px;
    border-radius: {{radius.sm}};
    margin: 1px 2px;
    min-height: 24px;
}
QMenu::item:selected {
    background-color: {{accent.bg.subtle}};
    color: {{text.primary}};
}
QMenu::separator {
    height: 1px;
    background-color: {{border.subtle}};
    margin: 3px 6px;
}

/* ===== ToolBar ===== */
QToolBar {
    background-color: {{bg.surface}};
    border: none;
    border-bottom: 1px solid {{border.subtle}};
    spacing: 1px;
    padding: 3px 6px;
}
QToolBar::separator {
    width: 1px;
    background-color: {{border.subtle}};
    margin: 4px 3px;
}
/* 現行実装は QPushButton ベース（Phase 3 で QToolButton 化） */
QToolBar QPushButton {
    background-color: transparent;
    color: {{text.primary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    padding: 4px 8px;
    font-size: {{font.size.md}};
    min-width: 28px;
    min-height: 28px;
}
QToolBar QPushButton:hover {
    background-color: {{bg.card.hover}};
    border-color: {{motion.hover.border}};
    padding-top: 3px;
    padding-bottom: 5px;
}
QToolBar QPushButton:pressed {
    background-color: {{bg.pressed}};
}
QToolBar QPushButton:checked {
    background-color: {{accent.bg.subtle}};
    color: {{accent.primary}};
}
QToolBar QPushButton:disabled {
    color: {{text.disabled}};
}
/* Phase 3 以降の QToolButton 対応 */
QToolBar QToolButton {
    background-color: transparent;
    color: {{text.primary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    padding: 4px 8px;
    min-width: 28px;
    min-height: 28px;
}
QToolBar QToolButton:hover {
    background-color: {{bg.card.hover}};
    border-color: {{motion.hover.border}};
    padding-top: 3px;
    padding-bottom: 5px;
}
QToolBar QToolButton:pressed {
    background-color: {{bg.pressed}};
}
QToolBar QToolButton:checked {
    background-color: {{accent.bg.subtle}};
    color: {{accent.primary}};
}
QToolBar QToolButton:disabled {
    color: {{text.disabled}};
}
QToolBar QComboBox {
    background-color: {{bg.surface}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 2px 8px;
    min-height: 26px;
}
QToolBar QComboBox:hover {
    border-color: {{border.strong}};
}
QToolBar QComboBox::drop-down {
    border: none;
    width: 16px;
}
QToolBar QLineEdit {
    background-color: {{bg.surface}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 2px 8px;
    min-height: 26px;
}
QToolBar QLineEdit:focus {
    border-color: {{accent.primary}};
}

/* ===== Navigation bar ===== */
#navBar {
    background-color: {{bg.surface}};
    border-bottom: 1px solid {{border.subtle}};
}
#navBtn {
    background-color: transparent;
    color: {{text.secondary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    font-size: {{font.size.lg}};
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    padding: 0;
}
#navBtn:hover {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border-color: {{motion.hover.border}};
}
#navBtn:pressed {
    background-color: {{bg.pressed}};
}
#navBtn:disabled {
    color: {{text.disabled}};
}
#addressBar {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    padding: 3px 10px;
    font-size: {{font.size.md}};
    min-height: 26px;
    selection-background-color: {{accent.selection.bg}};
    selection-color: {{text.primary}};
}
#addressBar:focus {
    border-color: {{accent.primary}};
}
#addressBar:hover {
    border-color: {{border.strong}};
}
#addressStack {
    background-color: transparent;
    border: none;
}
#breadcrumbBar {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    min-height: 30px;
}
#breadcrumbBar:hover {
    border-color: {{border.strong}};
}
#breadcrumbSegment {
    background-color: transparent;
    color: {{text.primary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    padding: 2px 7px;
    min-height: 22px;
    font-size: {{font.size.md}};
}
#breadcrumbSegment:hover {
    background-color: {{bg.hover}};
    border-color: {{motion.hover.border}};
}
#breadcrumbSegment:pressed {
    background-color: {{bg.pressed}};
}
#breadcrumbSeparator {
    color: {{text.disabled}};
    padding: 0 1px;
    background: transparent;
}
#breadcrumbCurrent {
    color: {{text.secondary}};
    padding: 2px 7px;
    background: transparent;
}

/* ===== Drive bar ===== */
#driveBar {
    background-color: {{bg.muted}};
    border-bottom: 1px solid {{border.strong}};
    min-height: 52px;
}
#driveBar QLabel {
    color: {{text.secondary}};
    font-size: {{font.size.sm}};
    font-weight: {{font.weight.semibold}};
    background: transparent;
}

#foldersLabel {
    color: {{text.secondary}};
    font-size: {{font.size.xs}};
    font-weight: {{font.weight.semibold}};
    letter-spacing: 1.2px;
    background-color: transparent;
}
#driveBar QPushButton {
    background-color: {{bg.window}};
    color: {{text.primary}};
    border: 1px solid {{border.strong}};
    border-radius: {{radius.sm}};
    padding: 0px 6px;
    min-width: 32px;
    min-height: {{size.drive.btn.h}};
    max-height: {{size.drive.btn.h}};
    font-size: {{font.size.md}};
    font-weight: {{font.weight.semibold}};
}
#driveBar QPushButton:hover {
    background-color: {{bg.card.hover}};
    border-color: {{accent.primary}};
    color: {{accent.hover}};
}
#driveBar QPushButton:pressed {
    background-color: {{accent.primary}};
    border-color: {{accent.primary}};
    color: {{accent.on}};
}
#driveBar QPushButton:checked {
    background-color: {{accent.primary}};
    color: {{accent.on}};
    border-color: {{accent.primary}};
    font-weight: 700;
}
#driveBar QPushButton:checked:hover {
    background-color: {{accent.hover}};
    border-color: {{accent.hover}};
    color: {{accent.on}};
}

/* ===== Left pane (tree panel) ===== */
#treePanel {
    background-color: {{bg.sidebar}};
    border-right: 1px solid {{border.subtle}};
}
#leftPane {
    background-color: {{bg.sidebar}};
}
#treePanel #foldersLabel {
    color: {{text.disabled}};
    font-size: {{font.size.xs}};
    font-weight: {{font.weight.semibold}};
    letter-spacing: 1.2px;
    padding: 0px 12px;
    min-height: 34px;
    border-bottom: 1px solid {{border.subtle}};
    background-color: {{bg.sidebar}};
}

/* ===== TreeView (汎用 / ファイルリスト基底) ===== */
QTreeView {
    background-color: {{bg.sidebar}};
    border: none;
    color: {{text.primary}};
    alternate-background-color: {{bg.subtle}};
    selection-background-color: {{accent.selection.bg}};
    selection-color: {{text.primary}};
    outline: none;
    show-decoration-selected: 1;
}
QTreeView::item {
    padding: 3px 4px;
    border-radius: {{radius.xs}};
    min-height: {{size.row.h}};
}
QTreeView::item:hover {
    background-color: {{bg.card.hover}};
    border: 1px solid {{motion.hover.border}};
}
QTreeView::item:selected {
    background-color: {{accent.selection.bg}};
    color: {{accent.primary}};
}
QTreeView::item:selected:!active {
    background-color: {{bg.muted}};
    color: {{text.primary}};
}
QTreeView::branch {
    background: transparent;
}
QTreeView::branch:hover {
    background-color: {{bg.hover}};
}

/* ===== フォルダツリー専用スタイル ===== */
QTreeView#folderTree {
    background-color: transparent;
    border: none;
    alternate-background-color: transparent;
    selection-color: {{accent.primary}};
}
QTreeView#folderTree::item {
    padding: 5px 6px 5px 2px;
    border-radius: {{radius.xs}};
    min-height: {{size.folder.row.h}};
    border: none;
}
QTreeView#folderTree::item:hover {
    background-color: {{bg.hover}};
    border: none;
}
QTreeView#folderTree::item:selected {
    background-color: {{accent.bg.subtle}};
    color: {{accent.hover}};
}
QTreeView#folderTree::item:selected:!active {
    background-color: {{bg.muted}};
    color: {{text.secondary}};
}
QTreeView#folderTree::branch {
    background: transparent;
}

/* ===== File list view ===== */
QTreeView#fileList {
    background-color: {{bg.card}};
    alternate-background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    outline: none;
    selection-background-color: {{accent.selection.bg}};
    selection-color: {{text.primary}};
    show-decoration-selected: 1;
}
QTreeView#fileList::item {
    padding: 3px 6px;
    min-height: {{size.row.h}};
    border-radius: {{radius.xs}};
}
QTreeView#fileList::item:hover {
    background-color: {{bg.card.hover}};
    border: 1px solid {{motion.hover.border}};
}
QTreeView#fileList::item:selected {
    background-color: {{accent.selection.bg}};
    color: {{text.primary}};
}
QTreeView#fileList::item:selected:!active {
    background-color: {{bg.muted}};
    color: {{text.primary}};
}

/* ===== HeaderView ===== */
QHeaderView {
    background-color: {{bg.surface}};
    border: none;
}
QHeaderView::section {
    background-color: {{bg.surface}};
    color: {{text.secondary}};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {{border.subtle}};
    border-bottom: 1px solid {{border.subtle}};
    font-size: {{font.size.xs}};
    font-weight: {{font.weight.semibold}};
    letter-spacing: 0.3px;
}
QHeaderView::section:hover {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
}
QHeaderView::section:first {
    border-left: none;
}

/* ===== ScrollBar ===== */
QScrollBar:vertical {
    background: transparent;
    width: {{size.scrollbar.thin}};
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: {{border.strong}};
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: {{text.secondary}};
    border-radius: 5px;
}
QScrollBar:vertical:hover {
    width: {{size.scrollbar.thick}};
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
    height: {{size.scrollbar.thin}};
    margin: 0 2px;
}
QScrollBar::handle:horizontal {
    background: {{border.strong}};
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: {{text.secondary}};
    border-radius: 5px;
}
QScrollBar:horizontal:hover {
    height: {{size.scrollbar.thick}};
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ファイルリストはスクロールバーを少し太く・常時はっきり表示 */
QTreeView#fileList QScrollBar:vertical {
    width: 10px;
    margin: 2px 1px 2px 0;
}
QTreeView#fileList QScrollBar:vertical:hover {
    width: 12px;
}
QTreeView#fileList QScrollBar::handle:vertical {
    background: {{border.strong}};
    border-radius: 5px;
    min-height: 32px;
}
QTreeView#fileList QScrollBar::handle:vertical:hover {
    background: {{text.secondary}};
}

/* ===== Splitter ===== */
QSplitter {
    background: transparent;
}
QSplitter::handle:horizontal {
    background-color: {{border.subtle}};
    width: 2px;
}
QSplitter::handle:horizontal:hover {
    background-color: {{accent.primary}};
}
QSplitter::handle:vertical {
    background-color: {{border.subtle}};
    height: 1px;
}
QSplitter::handle:vertical:hover {
    background-color: {{accent.primary}};
}

/* ===== ProgressBar ===== */
QProgressBar {
    background-color: {{bg.muted}};
    border: none;
    border-radius: 2px;
    text-align: center;
    color: transparent;
    max-height: 3px;
}
QProgressBar::chunk {
    background-color: {{accent.primary}};
    border-radius: 2px;
}

/* ===== General QPushButton ===== */
QPushButton {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.sm}};
    padding: 5px 14px;
    font-size: {{font.size.md}};
    min-height: {{size.button.h}};
}
QPushButton:hover {
    background-color: {{bg.card.hover}};
    border-color: {{motion.hover.border}};
    padding-top: 4px;
    padding-bottom: 6px;
}
QPushButton:pressed {
    background-color: {{bg.pressed}};
    border-color: {{border.strong}};
}
QPushButton:checked {
    background-color: {{accent.bg.subtle}};
    border-color: {{accent.primary}};
    color: {{accent.primary}};
}
QPushButton:disabled {
    color: {{text.disabled}};
    background-color: {{bg.muted}};
    border-color: {{border.subtle}};
}
QPushButton:default {
    background-color: {{accent.primary}};
    border-color: {{accent.primary}};
    color: #FFFFFF;
}
QPushButton:default:hover {
    background-color: {{accent.hover}};
    border-color: {{accent.hover}};
}

/* ===== ComboBox ===== */
QComboBox {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 3px 10px;
    min-height: {{size.input.h}};
}
QComboBox:hover {
    border-color: {{border.strong}};
}
QComboBox:focus {
    border-color: {{accent.primary}};
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.md}};
    padding: 3px;
    selection-background-color: {{accent.selection.bg}};
    selection-color: {{text.primary}};
    outline: none;
}

/* ===== LineEdit ===== */
QLineEdit {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 4px 10px;
    font-size: {{font.size.md}};
    min-height: {{size.input.h}};
    selection-background-color: {{accent.selection.bg}};
    selection-color: {{text.primary}};
}
QLineEdit:focus {
    border-color: {{accent.primary}};
}
QLineEdit:hover {
    border-color: {{border.strong}};
}
QLineEdit:disabled {
    color: {{text.disabled}};
    background-color: {{bg.muted}};
}

/* ===== SpinBox ===== */
QSpinBox, QDoubleSpinBox {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 3px 8px;
    min-height: {{size.input.h}};
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: {{accent.primary}};
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: {{bg.subtle}};
    border: none;
    border-radius: 3px;
    width: 14px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: {{bg.pressed}};
}

/* ===== FontComboBox ===== */
QFontComboBox {
    background-color: {{bg.card}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 3px 8px;
    min-height: {{size.input.h}};
}
QFontComboBox:hover {
    border-color: {{border.strong}};
}
QFontComboBox:focus {
    border-color: {{accent.primary}};
}

/* ===== CheckBox ===== */
QCheckBox {
    color: {{text.primary}};
    spacing: 7px;
    font-size: {{font.size.md}};
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: {{radius.xs}};
    border: 1px solid {{border.strong}};
    background-color: {{bg.card}};
}
QCheckBox::indicator:hover {
    border-color: {{accent.primary}};
}
QCheckBox::indicator:checked {
    background-color: {{accent.primary}};
    border-color: {{accent.primary}};
    image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png);
}
QCheckBox::indicator:disabled {
    border-color: {{border.glass}};
    background-color: {{bg.card}};
}

/* ===== RadioButton ===== */
QRadioButton {
    color: {{text.primary}};
    spacing: 7px;
    font-size: {{font.size.md}};
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {{border.strong}};
    background-color: {{bg.card}};
}
QRadioButton::indicator:hover {
    border-color: {{accent.primary}};
}
QRadioButton::indicator:checked {
    background-color: {{accent.primary}};
    border-color: {{accent.primary}};
}

/* ===== Label ===== */
QLabel {
    color: {{text.primary}};
    font-size: {{font.size.md}};
    background: transparent;
}

/* ===== GroupBox ===== */
QGroupBox {
    color: {{text.secondary}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    margin-top: 14px;
    padding-top: 10px;
    padding-bottom: 6px;
    font-size: {{font.size.sm}};
    font-weight: {{font.weight.semibold}};
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 0px;
    color: {{text.secondary}};
    background-color: transparent;
    padding: 0 5px;
}

/* ===== TabWidget ===== */
QTabWidget::pane {
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    background-color: {{bg.card}};
    top: -1px;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background-color: {{bg.card}};
    color: {{text.secondary}};
    padding: 6px 16px;
    border: 1px solid {{border.subtle}};
    border-bottom: none;
    margin-right: 1px;
    font-size: {{font.size.sm}};
    font-weight: {{font.weight.semibold}};
}
QTabBar::tab:selected {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border-color: {{border.subtle}};
    border-bottom-color: {{bg.surface}};
}
QTabBar::tab:hover:!selected {
    color: {{text.primary}};
    background-color: {{bg.hover}};
}

/* ===== Dialog ===== */
QDialog {
    background-color: {{bg.window}};
}

/* ===== ListWidget ===== */
QListWidget {
    background-color: {{bg.card}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
    color: {{text.primary}};
    alternate-background-color: {{bg.subtle}};
    outline: none;
}
QListWidget::item {
    padding: 4px 8px;
    border-radius: {{radius.xs}};
    margin: 1px 3px;
    min-height: 22px;
}
QListWidget::item:hover {
    background-color: {{bg.card.hover}};
    border: 1px solid {{motion.hover.border}};
}
QListWidget::item:selected {
    background-color: {{accent.selection.bg}};
    color: {{accent.primary}};
}

/* ===== StatusBar ===== */
QStatusBar {
    background-color: {{bg.surface}};
    color: {{text.secondary}};
    border-top: 1px solid {{border.subtle}};
    font-size: {{font.size.xs}};
    padding: 1px 8px;
}
QStatusBar::item {
    border: none;
}
#statusPathLabel {
    color: {{text.secondary}};
    font-size: {{font.size.xs}};
    background: transparent;
}

/* ===== ToolTip ===== */
QToolTip {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.sm}};
    padding: 3px 8px;
    font-size: {{font.size.sm}};
}

/* ===== Frame ===== */
QFrame {
    background-color: transparent;
    border: none;
}

/* ===== Bento / Preview cards ===== */
#rightPane {
    background-color: transparent;
}

#bentoGrid {
    background-color: transparent;
}

QFrame#bentoCard,
QFrame#thumbnail-card,
#video-thumbnail-preview {
    background-color: {{bg.card}};
    border: 1px solid {{border.glass}};
    border-radius: {{radius.md}};
}

QFrame#bentoCard:hover,
QFrame#thumbnail-card:hover,
#video-thumbnail-preview:hover {
    background-color: {{bg.card.hover}};
    border-color: {{motion.hover.border}};
}

#thumbnail-title {
    color: {{text.primary}};
    font-size: {{font.size.sm}};
    font-weight: {{font.weight.semibold}};
}

#bentoTitle {
    color: {{text.secondary}};
    font-size: {{font.size.xs}};
    font-weight: {{font.weight.semibold}};
}

#bentoValue {
    color: {{text.primary}};
    font-size: {{font.size.sm}};
    font-weight: {{font.weight.medium}};
}

QScrollArea#thumbnail-scroll-area {
    background-color: transparent;
    border: none;
}

/* ===== VideoPlayer ===== */
#vpStatusLabel {
    color: {{text.secondary}};
    font-size: {{font.size.sm}};
    padding: 3px 10px;
    background: transparent;
}
#vpControlBar {
    background-color: {{bg.card}};
    border-top: 1px solid {{border.subtle}};
}
QSlider#vpSeekSlider {
    margin: 0;
}
QSlider#vpSeekSlider::groove:horizontal {
    background-color: {{bg.muted}};
    height: 3px;
    border-radius: 2px;
    margin: 1px 0;
}
QSlider#vpSeekSlider::sub-page:horizontal {
    background-color: {{accent.primary}};
    border-radius: 2px;
}
QSlider#vpSeekSlider::handle:horizontal {
    background-color: {{accent.primary}};
    width: 10px;
    height: 10px;
    border-radius: 5px;
    margin: -4px 0;
}
QSlider#vpSeekSlider::handle:horizontal:hover {
    width: 13px;
    height: 13px;
    border-radius: 7px;
    margin: -5px 0;
}
/* アイコン的な小型ボタン（▶ ⏸ ✕ など） */
QPushButton#vpIconBtn {
    background-color: transparent;
    color: {{text.primary}};
    border: none;
    border-radius: {{radius.xs}};
    font-size: 14px;
    padding: 0;
}
QPushButton#vpIconBtn:hover {
    background-color: {{bg.hover}};
}
QPushButton#vpIconBtn:pressed {
    background-color: {{bg.pressed}};
}
/* サブアクション用の小型テキストボタン */
QPushButton#vpSubBtn {
    background-color: transparent;
    color: {{text.secondary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.xs}};
    font-size: {{font.size.xs}};
    padding: 1px 8px;
    min-height: 20px;
    max-height: 20px;
}
QPushButton#vpSubBtn:hover {
    background-color: {{bg.card.hover}};
    color: {{text.primary}};
    border-color: {{motion.hover.border}};
}
QPushButton#vpSubBtn:disabled {
    color: {{text.disabled}};
    border-color: {{border.subtle}};
}
/* 時刻表示 */
#vpTimeLabel {
    color: {{text.secondary}};
    font-size: {{font.size.sm}};
    font-family: {{font.family.mono}};
    background: transparent;
}
/* 速度コンボ */
QComboBox#vpSpeedCombo {
    background-color: transparent;
    color: {{text.secondary}};
    border: 1px solid {{border.subtle}};
    border-radius: {{radius.xs}};
    font-size: {{font.size.xs}};
    padding: 0px 4px;
    min-height: 20px;
    max-height: 20px;
    min-width: 52px;
    max-width: 52px;
}
QComboBox#vpSpeedCombo:hover {
    border-color: {{border.strong}};
    color: {{text.primary}};
}
QComboBox#vpSpeedCombo::drop-down {
    border: none;
    width: 12px;
}

/* ===== Focus ring ===== */
/* 入力系: フォーカス時にアクセント色のボーダーでリング表示 */
QPushButton:focus {
    border-color: {{accent.primary}};
    outline: none;
}
QRadioButton:focus::indicator {
    border-color: {{accent.primary}};
}
/* QTreeView / QListView のデフォルト点線フォーカスは outline: none で抑制 */
/* 選択色でフォーカス状態を示す */
QTreeView:focus {
    outline: none;
}
QListWidget:focus {
    outline: none;
}
"""

# ── ビルド関数 ─────────────────────────────────────────────────────────


def build_qss(tokens: dict[str, str]) -> str:
    """トークン辞書を QSS テンプレートに展開して返す。"""
    qss = _QSS_TEMPLATE
    for key, value in tokens.items():
        qss = qss.replace("{{" + key + "}}", value)
    return qss


# ── システム判定 ───────────────────────────────────────────────────────


def _is_dark_system() -> bool:
    """Windows の "アプリのモード" がダークかどうかを判定する。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
    except Exception:
        return False


# ── 設定読み書き ───────────────────────────────────────────────────────


def get_saved_mode() -> ThemeMode:
    """QSettings から保存済みテーマモードを読み出す（デフォルト: light）。

    レジストリ経由で bytes が返る場合や不正値の場合は "light" にフォールバックする。
    """
    from PySide6.QtCore import QSettings
    settings = QSettings("FileManager", "Settings")
    raw = settings.value("ui/theme_mode", "light")
    val = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    return val if val in ("light", "dark", "system") else "light"  # type: ignore[return-value]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex_safe(r: int, g: int, b: int) -> str:
    return f"#{min(255,max(0,r)):02X}{min(255,max(0,g)):02X}{min(255,max(0,b)):02X}"


_HOVER_DELTA_DARK  = 30   # ダークモード: 加算で明るくする量（飽和色でも有効）
_HOVER_DELTA_LIGHT = 25   # ライトモード: 減算で暗くする量


def _derive_accent_tokens(hex_color: str, is_dark: bool) -> dict[str, str]:
    """アクセントカラーから hover / bg.subtle / selection.bg トークンを派生させる。"""
    r, g, b = _hex_to_rgb(hex_color)
    if is_dark:
        # 乗算ではなく加算で明るくすることで飽和色・純黒でも変化が出る
        hover = _rgb_to_hex_safe(r + _HOVER_DELTA_DARK, g + _HOVER_DELTA_DARK, b + _HOVER_DELTA_DARK)
        sel_bg = _rgb_to_hex_safe(int(r * 0.25), int(g * 0.25), int(b * 0.25))
    else:
        # 減算で暗くすることで飽和色でも変化が出る
        hover = _rgb_to_hex_safe(r - _HOVER_DELTA_LIGHT, g - _HOVER_DELTA_LIGHT, b - _HOVER_DELTA_LIGHT)
        sel_bg = _rgb_to_hex_safe(
            255 - int((255 - r) * 0.15),
            255 - int((255 - g) * 0.15),
            255 - int((255 - b) * 0.15),
        )
    return {
        "accent.primary":      hex_color,
        "accent.hover":        hover,
        "accent.bg.subtle":    f"rgba({r},{g},{b},{0.16 if is_dark else 0.10})",
        "accent.selection.bg": sel_bg,
    }


def get_system_accent_color() -> str | None:
    """Windows レジストリから SystemAccentColor を読み出し #RRGGBB 形式で返す。

    取得できない場合は None を返す。
    レジストリ値は 0xAABBGGRR（リトルエンディアン BGR）形式。
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\DWM",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            v = int(val) & 0xFFFFFFFF
            r = (v >> 0) & 0xFF
            g = (v >> 8) & 0xFF
            b = (v >> 16) & 0xFF
            return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return None


def _is_mica_capable() -> bool:
    """Windows 11 22H2+ (build >= 22621) かどうかを返す。"""
    if sys.platform != "win32":
        return False
    try:
        import platform
        import re as _re
        parts = platform.version().split(".")
        last = parts[-1] if parts else "0"
        m = _re.match(r"(\d+)", last)
        build = int(m.group(1)) if m else 0
        return build >= 22621
    except Exception:
        return False


def try_enable_mica(hwnd: int) -> bool:
    """Windows 11 22H2+ (build >= 22621) で Mica バックドロップを有効化する。

    Returns:
        True if Mica was successfully enabled, False otherwise.
    """
    if not _is_mica_capable():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2  # Mica
        value = ctypes.c_int(DWMSBT_MAINWINDOW)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return hr == 0  # S_OK
    except Exception:
        return False


# Mica 有効時に QMainWindow だけ透明にする追加 QSS
# QWidget { background } より後に適用され、QMainWindow 固有ルールとして上書きされる
_QSS_MICA_OVERRIDE = """
/* ===== Mica override: QMainWindow 背景を透明化 ===== */
QMainWindow {
    background-color: transparent;
}
"""


def apply_theme(
    app,
    mode: ThemeMode | None = None,
    accent_color: str | None = None,
    mica_active: bool = False,
) -> None:
    """アプリ全体に指定テーマを適用し、QSettings に mode を保存する。

    Args:
        app:          QApplication インスタンス
        mode:         "light" | "dark" | "system"。None のとき QSettings から読む。
        accent_color: 明示指定のアクセント色（#RRGGBB）。None のとき QSettings の
                      ui/accent_mode を参照し "system" なら OS から、
                      "custom" なら ui/accent_color から取得する。
        mica_active:  True のとき QMainWindow 背景を透明にして Mica を透過させる。
    """
    from PySide6.QtCore import QSettings
    settings = QSettings("FileManager", "Settings")

    if mode is None:
        mode = get_saved_mode()

    is_dark = (mode == "dark") or (mode == "system" and _is_dark_system())
    tokens = dict(TOKENS_DARK if is_dark else TOKENS_LIGHT)

    # アクセントカラーの解決
    if accent_color is None:
        raw_am = settings.value("ui/accent_mode", "default")
        accent_mode = raw_am.decode() if isinstance(raw_am, (bytes, bytearray)) else str(raw_am)
        if accent_mode == "system":
            accent_color = get_system_accent_color()
        elif accent_mode == "custom":
            saved = settings.value("ui/accent_color", None)
            if isinstance(saved, str) and saved.startswith("#") and len(saved) == 7:
                accent_color = saved

    if accent_color is not None:
        tokens.update(_derive_accent_tokens(accent_color, is_dark))

    qss = build_qss(tokens)
    if mica_active:
        qss += _QSS_MICA_OVERRIDE

    app.setStyleSheet(qss)
    settings.setValue("ui/theme_mode", mode)
