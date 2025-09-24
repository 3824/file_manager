#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡単なテスト例
"""

import os
import sys
import tempfile
import pytest

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_simple():
    """簡単なテスト"""
    assert 1 + 1 == 2

def test_imports():
    """必要なモジュールのインポートテスト"""
    try:
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        import tempfile
        assert True
    except ImportError as e:
        pytest.fail(f"Import failed: {e}")

def test_settings_creation():
    """QSettingsの作成テスト"""
    try:
        from PySide6.QtCore import QSettings
        
        # 一時的な設定を作成
        with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
            settings_file = f.name
        
        # ファイルベースの設定を作成
        settings = QSettings(settings_file, QSettings.IniFormat)
        settings.setValue("test_key", "test_value")
        settings.sync()
        
        # 値を読み取り
        value = settings.value("test_key", type=str)
        assert value == "test_value"
        
        # クリーンアップ
        os.unlink(settings_file)
        
    except Exception as e:
        pytest.fail(f"QSettings test failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
