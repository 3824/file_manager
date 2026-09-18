import string
from PySide6.QtWidgets import QMessageBox


def silent_question(parent, title, message, buttons=None, default=None):
    """音を鳴らさない確認ダイアログ（QMessageBox.question の代替）"""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(message)
    mb.setIcon(QMessageBox.Icon.NoIcon)
    if buttons is not None:
        mb.setStandardButtons(buttons)
    else:
        mb.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if default is not None:
        mb.setDefaultButton(default)
    return mb.exec()


def silent_information(parent, title, message):
    """音を鳴らさない情報ダイアログ（QMessageBox.information の代替）"""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(message)
    mb.setIcon(QMessageBox.Icon.NoIcon)
    mb.setStandardButtons(QMessageBox.StandardButton.Ok)
    mb.exec()


def silent_warning(parent, title, message):
    """音を鳴らさない警告ダイアログ（QMessageBox.warning の代替）"""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(message)
    mb.setIcon(QMessageBox.Icon.NoIcon)
    mb.setStandardButtons(QMessageBox.StandardButton.Ok)
    mb.exec()


def silent_critical(parent, title, message):
    """音を鳴らさないエラーダイアログ（QMessageBox.critical の代替）"""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(message)
    mb.setIcon(QMessageBox.Icon.NoIcon)
    mb.setStandardButtons(QMessageBox.StandardButton.Ok)
    mb.exec()

def coerce_bool(value, default):
    """設定値を真偽値に変換"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default

def coerce_int(value, default, *, minimum=None, maximum=None):
    """設定値を整数に変換し、範囲内に収めて返す。"""
    candidate = default
    try:
        if value is None:
            candidate = default
        elif isinstance(value, bool):
            candidate = int(value)
        elif isinstance(value, int):
            candidate = value
        elif isinstance(value, float):
            candidate = int(value)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped:
                candidate = int(stripped)
    except (ValueError, TypeError):
        candidate = default
    if minimum is not None:
        candidate = max(candidate, minimum)
    if maximum is not None:
        candidate = min(candidate, maximum)
    return candidate

def coerce_str(value, default):
    """設定値を文字列に変換"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)

def coerce_color(value, default):
    """色設定を#RRGGBB形式に変換"""
    candidate = coerce_str(value, default).strip()
    if (
        len(candidate) == 7
        and candidate.startswith("#")
        and all(c in string.hexdigits for c in candidate[1:])
    ):
        return candidate.upper()
    return default
