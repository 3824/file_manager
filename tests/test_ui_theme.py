"""ui_theme モジュールの単体テスト（非 UI）。"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_manager.ui_theme import (
    TOKENS_DARK, TOKENS_LIGHT, build_qss,
    _derive_accent_tokens, _hex_to_rgb, _rgb_to_hex_safe,
    get_system_accent_color, try_enable_mica,
)

_REQUIRED_KEYS = [
    "bg.window",
    "bg.surface",
    "bg.card",
    "bg.card.hover",
    "bg.sidebar",
    "bg.hover",
    "bg.pressed",
    "border.subtle",
    "text.primary",
    "text.secondary",
    "text.disabled",
    "accent.primary",
    "accent.selection.bg",
    "font.size.md",
    "font.family.ui",
    "radius.sm",
    "size.button.h",
    "size.row.h",
    "motion.hover.border",
]

_REQUIRED_SELECTORS = [
    "QWidget",
    "QMenuBar",
    "QToolBar QPushButton",
    "QToolBar QToolButton",
    "QTreeView#fileList",
    "#navBar",
    "#driveBar",
    "#addressBar",
    "#treePanel",
    "QHeaderView",
    "QScrollBar:vertical",
    "QSplitter",
    "QPushButton",
    "QLineEdit",
    "QComboBox",
    "QStatusBar",
    "#statusPathLabel",
    "#bentoGrid",
    "QFrame#bentoCard",
    "QToolTip",
]


def test_light_no_unresolved_placeholders():
    qss = build_qss(TOKENS_LIGHT)
    unresolved = re.findall(r"\{\{[^}]+\}\}", qss)
    assert not unresolved, f"TOKENS_LIGHT: 未置換トークン {unresolved}"


def test_dark_no_unresolved_placeholders():
    qss = build_qss(TOKENS_DARK)
    unresolved = re.findall(r"\{\{[^}]+\}\}", qss)
    assert not unresolved, f"TOKENS_DARK: 未置換トークン {unresolved}"


def test_light_has_required_keys():
    for key in _REQUIRED_KEYS:
        assert key in TOKENS_LIGHT, f"TOKENS_LIGHT に {key!r} がない"


def test_dark_has_required_keys():
    for key in _REQUIRED_KEYS:
        assert key in TOKENS_DARK, f"TOKENS_DARK に {key!r} がない"


def test_light_and_dark_same_keys():
    assert set(TOKENS_LIGHT.keys()) == set(TOKENS_DARK.keys()), (
        "TOKENS_LIGHT と TOKENS_DARK のキーが一致しない"
    )


def test_qss_contains_required_selectors():
    qss = build_qss(TOKENS_LIGHT)
    for selector in _REQUIRED_SELECTORS:
        assert selector in qss, f"QSS に {selector!r} が含まれない"


def test_checkbox_indicator_is_explicitly_styled():
    """QCheckBox::indicator を無指定のままにすると、フルカスタムQSS環境下では
    ネイティブ描画が壊れて黒い四角として表示されてしまう（実際に報告されたバグ）。
    QRadioButton と同様に明示的にスタイルを与える。
    """
    qss = build_qss(TOKENS_LIGHT)
    assert "QCheckBox::indicator {" in qss
    assert "QCheckBox::indicator:checked" in qss
    assert "standardbutton-apply-16.png" in qss
    assert "data:image/svg+xml" not in qss


def test_build_qss_is_pure():
    """同じトークンを 2 回呼んでも同じ結果になる（副作用なし）。"""
    a = build_qss(TOKENS_LIGHT)
    b = build_qss(TOKENS_LIGHT)
    assert a == b


def test_dark_bg_is_dark():
    assert TOKENS_DARK["bg.window"].upper() in {"#0F172A", "#111827", "#1F2937"} or TOKENS_DARK[
        "bg.window"
    ].startswith("#1"), (
        f"ダークテーマの bg.window が明るすぎる: {TOKENS_DARK['bg.window']}"
    )


def test_light_bg_is_light():
    assert TOKENS_LIGHT["bg.window"].startswith("#F") or TOKENS_LIGHT["bg.window"].startswith("#E"), (
        f"ライトテーマの bg.window が暗すぎる: {TOKENS_LIGHT['bg.window']}"
    )


def test_partial_tokens_show_unresolved():
    """不完全なトークン辞書を渡すと未置換のプレースホルダが残ることを確認する。"""
    partial = {"bg.window": "#FFF"}  # 他のキーが欠落
    qss = build_qss(partial)
    unresolved = re.findall(r"\{\{[^}]+\}\}", qss)
    assert unresolved, "不完全なトークンで未置換が出ないのはおかしい"


# ── Phase 5: システムアクセントカラー / Mica ─────────────────────────────

def test_derive_accent_tokens_light_returns_all_keys():
    """_derive_accent_tokens がライトテーマで必要なキーをすべて返す。"""
    result = _derive_accent_tokens("#0078D4", is_dark=False)
    for key in ("accent.primary", "accent.hover", "accent.bg.subtle", "accent.selection.bg"):
        assert key in result, f"_derive_accent_tokens が {key!r} を返さない"


def test_derive_accent_tokens_dark_returns_all_keys():
    """_derive_accent_tokens がダークテーマで必要なキーをすべて返す。"""
    result = _derive_accent_tokens("#4CC2FF", is_dark=True)
    for key in ("accent.primary", "accent.hover", "accent.bg.subtle", "accent.selection.bg"):
        assert key in result


def test_derive_accent_tokens_preserves_primary():
    """accent.primary はそのまま渡した値が使われる。"""
    color = "#FF6600"
    result = _derive_accent_tokens(color, is_dark=False)
    assert result["accent.primary"] == color


def test_rgb_hex_roundtrip():
    """_hex_to_rgb と _rgb_to_hex_safe が往復変換でも値を保持する。"""
    original = "#1A2B3C"
    r, g, b = _hex_to_rgb(original)
    assert _rgb_to_hex_safe(r, g, b) == original


def test_rgb_to_hex_safe_clamps():
    """_rgb_to_hex_safe は 0–255 の範囲にクランプする。"""
    assert _rgb_to_hex_safe(-10, 300, 128) == "#00FF80"


def test_get_system_accent_color_returns_valid_or_none():
    """get_system_accent_color は #RRGGBB 形式か None を返す。"""
    result = get_system_accent_color()
    if result is not None:
        assert re.match(r"^#[0-9A-Fa-f]{6}$", result), f"不正な色形式: {result}"


def test_try_enable_mica_does_not_raise():
    """try_enable_mica は hwnd=0 で呼んでも例外を投げない。"""
    try:
        result = try_enable_mica(0)
        assert isinstance(result, bool)
    except Exception as exc:
        assert False, f"try_enable_mica が例外を投げた: {exc}"


def test_derive_accent_overrides_tokens():
    """_derive_accent_tokens の結果を TOKENS_LIGHT にマージすると未置換がない。"""
    tokens = dict(TOKENS_LIGHT)
    tokens.update(_derive_accent_tokens("#FF6600", is_dark=False))
    qss = build_qss(tokens)
    unresolved = re.findall(r"\{\{[^}]+\}\}", qss)
    assert not unresolved, f"アクセント上書き後に未置換トークン: {unresolved}"
