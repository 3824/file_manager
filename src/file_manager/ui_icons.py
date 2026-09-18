#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ツールバー・ウィジェット用アイコン管理モジュール。

qtawesome が利用できる場合は Font Awesome 6 Solid アイコンを返す。
利用できない場合は None を返し、呼び出し側で絵文字フォールバックを使う。
"""
from __future__ import annotations

try:
    import qtawesome as _qta
    _QTA_AVAILABLE = True
except ImportError:
    _qta = None  # type: ignore[assignment]
    _QTA_AVAILABLE = False

# ツールバーアイテム ID → Font Awesome 6 Solid アイコン名
_ICON_MAP: dict[str, str] = {
    "up":            "fa6s.arrow-up",
    "refresh":       "fa6s.rotate-right",
    "copy":          "fa6s.copy",
    "cut":           "fa6s.scissors",
    "paste":         "fa6s.paste",
    "delete":        "fa6s.xmark",       # 完全削除（ゴミ箱移動と区別するため ✕ 系アイコン）
    "rename":        "fa6s.pen",
    "new_folder":    "fa6s.folder-plus",
    "search":        "fa6s.magnifying-glass",
    "hidden":        "fa6s.eye",
    "disk_analysis": "fa6s.chart-pie",
    "dup_videos":    "fa6s.film",
    "similar_files": "fa6s.file-lines",
    "same_size":     "fa6s.scale-balanced",
    "video_player":  "fa6s.play",
    "trash":         "fa6s.trash-can",
    "settings":      "fa6s.gear",
    # ナビゲーションボタン
    "nav_back":      "fa6s.chevron-left",
    "nav_forward":   "fa6s.chevron-right",
    "nav_up":        "fa6s.arrow-up",
}

# テーマ別のデフォルトアイコン色
_DEFAULT_COLOR_LIGHT = "#5C5C5C"  # text.secondary (light)
_DEFAULT_COLOR_DARK  = "#CBD5E1"  # text.secondary (dark)


def _current_icon_color() -> str:
    """QSettings から現在のテーマモードを読み取りアイコン色を返す。"""
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings("FileManager", "Settings")
        mode = settings.value("ui/theme_mode", "dark")
        if isinstance(mode, (bytes, bytearray)):
            mode = mode.decode()
        return _DEFAULT_COLOR_DARK if mode == "dark" else _DEFAULT_COLOR_LIGHT
    except Exception:
        return _DEFAULT_COLOR_DARK


def get_icon(name: str, color: str | None = None):
    """アイコン名に対応する QIcon を返す。

    Args:
        name:  _ICON_MAP のキー（ツールバー ID またはナビ ID）。
        color: アイコン色。None のとき現在のテーマから自動取得。

    Returns:
        QIcon（qtawesome 利用可能時）、または None（フォールバック用）。
    """
    if not _QTA_AVAILABLE or name not in _ICON_MAP:
        return None
    resolved_color = color if color is not None else _current_icon_color()
    try:
        return _qta.icon(_ICON_MAP[name], color=resolved_color)
    except Exception:
        return None


def apply_icon_to_button(button, name: str, fallback_text: str, color: str | None = None) -> None:
    """ボタンにアイコンを設定する。

    qtawesome が利用できない場合は fallback_text をそのまま残す。

    Args:
        button:        QPushButton インスタンス。
        name:          _ICON_MAP のキー。
        fallback_text: qtawesome が利用できないときに使うテキスト（絵文字など）。
        color:         アイコン色（省略時は自動）。
    """
    from PySide6.QtCore import QSize
    icon = get_icon(name, color)
    if icon is not None:
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))
        button.setText("")
    else:
        button.setText(fallback_text)
