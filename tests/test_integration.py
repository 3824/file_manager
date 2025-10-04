#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定機能の統合テスト
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestSettingsIntegration:
    """設定機能の統合テストクラス"""
    
    def test_settings_cycle(self):
        """設定の保存→読み込みサイクルテスト"""
        from PySide6.QtCore import QSettings
        
        # 一時設定ファイル
        with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
            settings_file = f.name
        
        try:
            # 第1段階: 設定の保存
            settings1 = QSettings(settings_file, QSettings.IniFormat)
            
            test_settings = {
                "show_size": True,
                "show_type": False,
                "show_permissions": True,
                "view_mode": "detail",
                "show_hidden": True,
                "color_hidden": "#FF0000",
                "last_path": "/test/directory"
            }
            
            for key, value in test_settings.items():
                settings1.setValue(key, value)
            settings1.sync()
            
            # 第2段階: 設定の読み込み
            settings2 = QSettings(settings_file, QSettings.IniFormat)
            
            for key, expected_value in test_settings.items():
                if isinstance(expected_value, bool):
                    actual_value = settings2.value(key, type=bool)
                elif isinstance(expected_value, str):
                    actual_value = settings2.value(key, type=str)
                else:
                    actual_value = settings2.value(key)
                
                assert actual_value == expected_value, f"Settings cycle failed for {key}"
            
        finally:
            if os.path.exists(settings_file):
                os.unlink(settings_file)
    
    def test_default_settings_fallback(self):
        """デフォルト設定へのフォールバックテスト"""
        from PySide6.QtCore import QSettings
        
        # 存在しない設定ファイル
        non_existent_file = "/non/existent/path/settings.ini"
        settings = QSettings(non_existent_file, QSettings.IniFormat)
        
        # デフォルト値でのフォールバック
        defaults = {
            "show_size": (True, bool),
            "show_permissions": (False, bool),
            "view_mode": ("list", str),
            "show_hidden": (False, bool),
            "color_normal": ("#000000", str)
        }
        
        for key, (default_value, value_type) in defaults.items():
            actual_value = settings.value(key, default_value, type=value_type)
            assert actual_value == default_value
            assert isinstance(actual_value, value_type)
    
    def test_settings_partial_corruption(self):
        """設定ファイルの部分的な破損に対する耐性テスト"""
        from PySide6.QtCore import QSettings
        
        # 一時設定ファイル
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            settings_file = f.name
            # 部分的に破損したINIファイルを作成
            f.write("""[General]
show_size=true
show_type=invalid_value
view_mode=detail
broken_line_without_equals
color_hidden=#FF0000
show_permissions=
""")
        
        try:
            settings = QSettings(settings_file, QSettings.IniFormat)
            
            # 正常な値は正しく読み込まれる
            assert settings.value("show_size", type=bool) is True
            assert settings.value("view_mode", type=str) == "detail"
            assert settings.value("color_hidden", type=str) == "#FF0000"
            
            # 破損した値はデフォルトにフォールバック
            show_type = settings.value("show_type", True, type=bool)
            assert isinstance(show_type, bool)
            
            show_permissions = settings.value("show_permissions", False, type=bool)
            assert isinstance(show_permissions, bool)
            
        finally:
            if os.path.exists(settings_file):
                os.unlink(settings_file)
    
    def test_concurrent_settings_access(self):
        """設定への並行アクセステスト"""
        from PySide6.QtCore import QSettings
        
        # 一時設定ファイル
        with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
            settings_file = f.name
        
        try:
            # 複数のQSettingsインスタンスを作成
            settings1 = QSettings(settings_file, QSettings.IniFormat)
            settings2 = QSettings(settings_file, QSettings.IniFormat)
            
            # 異なるインスタンスから設定を書き込み
            settings1.setValue("test_key1", "value1")
            settings2.setValue("test_key2", "value2")
            
            settings1.sync()
            settings2.sync()
            
            # 新しいインスタンスで両方の値を読み取り
            settings3 = QSettings(settings_file, QSettings.IniFormat)
            
            assert settings3.value("test_key1", type=str) == "value1"
            assert settings3.value("test_key2", type=str) == "value2"
            
        finally:
            if os.path.exists(settings_file):
                os.unlink(settings_file)
    
    def test_settings_type_consistency(self):
        """設定値の型一貫性テスト"""
        from PySide6.QtCore import QSettings
        
        # 一時設定ファイル
        with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
            settings_file = f.name
        
        try:
            settings = QSettings(settings_file, QSettings.IniFormat)
            
            # 各種型の設定値をテスト
            test_values = {
                "bool_true": (True, bool),
                "bool_false": (False, bool),
                "string_value": ("test_string", str),
                "empty_string": ("", str),
                "int_value": (42, int),
                "float_value": (3.14, float)
            }
            
            # 書き込み
            for key, (value, _) in test_values.items():
                settings.setValue(key, value)
            settings.sync()
            
            # 読み込みと型チェック
            for key, (expected_value, expected_type) in test_values.items():
                actual_value = settings.value(key, type=expected_type)
                assert actual_value == expected_value, f"Value mismatch for {key}"
                assert isinstance(actual_value, expected_type), f"Type mismatch for {key}"
            
        finally:
            if os.path.exists(settings_file):
                os.unlink(settings_file)

def test_all_settings_tests():
    """全設定テストの実行"""
    # すべてのテストを組み合わせて実行
    integration_tests = TestSettingsIntegration()
    
    integration_tests.test_settings_cycle()
    integration_tests.test_default_settings_fallback()
    integration_tests.test_settings_partial_corruption()
    integration_tests.test_concurrent_settings_access()
    integration_tests.test_settings_type_consistency()
    
    # すべてのテストが成功
    assert True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
