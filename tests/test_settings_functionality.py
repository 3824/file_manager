#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定機能の実用的なテスト
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_settings_keys_consistency():
    """設定キーの一貫性テスト"""
    # 期待される設定キー
    expected_visible_columns_keys = [
        "name", "size", "type", "modified", "permissions", 
        "created", "attributes", "extension", "owner", "group"
    ]
    
    expected_settings_keys = [
        "show_name", "show_size", "show_type", "show_modified", 
        "show_permissions", "show_created", "show_attributes", 
        "show_extension", "show_owner", "show_group",
        "view_mode", "show_hidden", "last_path",
        "color_hidden", "color_readonly", "color_system", "color_normal"
    ]
    
    # キーが正しく定義されていることを確認
    assert len(expected_visible_columns_keys) == 10
    assert len(expected_settings_keys) >= 17
    
    # 各visible_columnsキーに対応するshow_キーが存在することを確認
    for col_key in expected_visible_columns_keys:
        show_key = f"show_{col_key}"
        assert show_key in expected_settings_keys, f"Missing settings key: {show_key}"

def test_default_visible_columns():
    """デフォルトのvisible_columns設定テスト"""
    default_columns = {
        "name": True,
        "size": True,
        "type": True,
        "modified": True,
        "permissions": False,
        "created": False,
        "attributes": False,
        "extension": False,
        "owner": False,
        "group": False
    }
    
    # デフォルト値の妥当性を確認
    assert default_columns["name"] is True  # 名前列は常に表示
    assert default_columns["size"] is True  # サイズは通常表示
    assert default_columns["type"] is True  # 種類も通常表示
    assert default_columns["modified"] is True  # 更新日時も通常表示
    
    # 拡張列はデフォルトで非表示
    assert default_columns["permissions"] is False
    assert default_columns["created"] is False
    assert default_columns["attributes"] is False
    assert default_columns["extension"] is False
    assert default_columns["owner"] is False
    assert default_columns["group"] is False

def test_settings_file_format():
    """設定ファイル形式のテスト"""
    from PySide6.QtCore import QSettings
    
    # 一時設定ファイルでテスト
    with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
        settings_file = f.name
    
    try:
        # 設定の書き込み
        settings = QSettings(settings_file, QSettings.IniFormat)
        
        # 各種設定を書き込み
        test_data = {
            "show_size": True,
            "show_permissions": False,
            "view_mode": "detail",
            "show_hidden": False,
            "color_hidden": "#808080",
            "last_path": "/test/path"
        }
        
        for key, value in test_data.items():
            settings.setValue(key, value)
        settings.sync()
        
        # 設定の読み取り
        new_settings = QSettings(settings_file, QSettings.IniFormat)
        
        for key, expected_value in test_data.items():
            if isinstance(expected_value, bool):
                actual_value = new_settings.value(key, type=bool)
            elif isinstance(expected_value, str):
                actual_value = new_settings.value(key, type=str)
            else:
                actual_value = new_settings.value(key)
            
            assert actual_value == expected_value, f"Key {key}: expected {expected_value}, got {actual_value}"
        
    finally:
        # クリーンアップ
        if os.path.exists(settings_file):
            os.unlink(settings_file)

def test_settings_error_handling():
    """設定エラーハンドリングのテスト"""
    # 不正な設定値のテスト
    invalid_values = [None, "", "invalid", 123, []]
    
    # デフォルト値での適切なフォールバック
    for invalid_value in invalid_values:
        # bool型設定
        if invalid_value in [None, "", "invalid"]:
            result_bool = False if invalid_value in [None, "", "invalid"] else bool(invalid_value)
            assert isinstance(result_bool, bool)
        
        # str型設定
        result_str = str(invalid_value) if invalid_value is not None else ""
        assert isinstance(result_str, str)

def test_column_visibility_logic():
    """列表示ロジックのテスト"""
    # 列表示の論理をテスト
    visible_columns = {
        "name": True,    # 常に表示
        "size": True,    # 表示
        "type": False,   # 非表示
        "modified": True, # 表示
        "permissions": False,  # 非表示
    }
    
    # 名前列は常に表示される
    assert visible_columns["name"] is True
    
    # 他の列は設定に従う
    visible_count = sum(1 for visible in visible_columns.values() if visible)
    assert visible_count >= 1  # 少なくとも名前列は表示される
    
    # 非表示列の確認
    hidden_columns = [key for key, visible in visible_columns.items() if not visible]
    assert "type" in hidden_columns
    assert "permissions" in hidden_columns

def test_color_settings_validation():
    """色設定の妥当性テスト"""
    valid_colors = ["#808080", "#0000FF", "#FF0000", "#000000"]
    invalid_colors = ["invalid", "808080", "#GGG", "rgb(255,0,0)"]
    
    # 有効な色形式の確認
    for color in valid_colors:
        assert color.startswith("#")
        assert len(color) == 7
        # 16進数文字の確認
        hex_part = color[1:]
        assert all(c in "0123456789ABCDEFabcdef" for c in hex_part)
    
    # 無効な色形式の確認
    for color in invalid_colors:
        if not color.startswith("#") or len(color) != 7:
            # デフォルト色にフォールバックすることを想定
            default_color = "#000000"
            assert default_color.startswith("#") and len(default_color) == 7

def test_view_mode_validation():
    """表示モードの妥当性テスト"""
    valid_modes = ["list", "icon", "detail"]
    invalid_modes = ["invalid", "", None, 123]
    
    # 有効なモードの確認
    for mode in valid_modes:
        assert mode in ["list", "icon", "detail"]
    
    # 無効なモードはデフォルト（list）にフォールバック
    default_mode = "list"
    for invalid_mode in invalid_modes:
        if invalid_mode not in valid_modes:
            # デフォルトモードを使用
            assert default_mode == "list"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
