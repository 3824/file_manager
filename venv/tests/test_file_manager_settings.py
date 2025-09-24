#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイルマネージャーの設定機能のテスト（修正版）
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_file_manager_import():
    """FileManagerWidgetのインポートテスト"""
    try:
        from file_manager import FileManagerWidget
        assert FileManagerWidget is not None
    except Exception as e:
        pytest.fail(f"FileManagerWidget import failed: {e}")

def test_settings_load_with_mock():
    """モックを使用した設定読み込みテスト"""
    with patch('PySide6.QtCore.QSettings') as mock_settings:
        with patch('PySide6.QtWidgets.QApplication'):
            with patch('file_manager.VideoDigestGenerator'):
                
                mock_settings_instance = MagicMock()
                mock_settings.return_value = mock_settings_instance
                
                # デフォルト値を返すモック設定
                def mock_value(key, default_value=None, type=None):
                    defaults = {
                        "show_size": True,
                        "show_type": True,
                        "show_modified": True,
                        "show_permissions": False,
                        "show_created": False,
                        "show_attributes": False,
                        "show_extension": False,
                        "show_owner": False,
                        "show_group": False,
                        "view_mode": "list",
                        "show_hidden": False,
                        "last_path": ""
                    }
                    return defaults.get(key, default_value)
                
                mock_settings_instance.value.side_effect = mock_value
                
                # ファイルマネージャーの初期化をテスト
                try:
                    from file_manager import FileManagerWidget
                    
                    # UIの初期化をスキップするためのパッチ
                    with patch.object(FileManagerWidget, 'init_ui'):
                        with patch.object(FileManagerWidget, 'setup_models'):
                            with patch.object(FileManagerWidget, 'connect_signals'):
                                with patch.object(FileManagerWidget, 'setup_context_menus'):
                                    with patch.object(FileManagerWidget, 'setup_custom_delegate'):
                                        with patch.object(FileManagerWidget, 'apply_settings'):
                                            widget = FileManagerWidget()
                    
                    # 設定が正しく読み込まれているかテスト
                    assert hasattr(widget, 'visible_columns')
                    assert widget.visible_columns["name"] is True
                    assert widget.visible_columns["size"] is True
                    assert widget.visible_columns["permissions"] is False
                    
                except Exception as e:
                    pytest.fail(f"FileManagerWidget initialization failed: {e}")

def test_settings_save_with_mock():
    """モックを使用した設定保存テスト"""
    with patch('PySide6.QtCore.QSettings') as mock_settings:
        with patch('PySide6.QtWidgets.QApplication'):
            with patch('file_manager.VideoDigestGenerator'):
                
                mock_settings_instance = MagicMock()
                mock_settings.return_value = mock_settings_instance
                mock_settings_instance.value.return_value = None
                
                try:
                    from file_manager import FileManagerWidget
                    
                    # UIの初期化をスキップ
                    with patch.object(FileManagerWidget, 'init_ui'):
                        with patch.object(FileManagerWidget, 'setup_models'):
                            with patch.object(FileManagerWidget, 'connect_signals'):
                                with patch.object(FileManagerWidget, 'setup_context_menus'):
                                    with patch.object(FileManagerWidget, 'setup_custom_delegate'):
                                        with patch.object(FileManagerWidget, 'apply_settings'):
                                            widget = FileManagerWidget()
                    
                    # 設定を変更
                    widget.visible_columns["permissions"] = True
                    widget.view_mode = "detail"
                    
                    # 設定保存をテスト
                    widget.save_settings()
                    
                    # 保存が呼ばれたことを確認
                    mock_settings_instance.setValue.assert_called()
                    mock_settings_instance.sync.assert_called_once()
                    
                except Exception as e:
                    pytest.fail(f"Settings save test failed: {e}")

def test_visible_columns_structure():
    """visible_columns辞書の構造テスト"""
    with patch('PySide6.QtCore.QSettings') as mock_settings:
        with patch('PySide6.QtWidgets.QApplication'):
            with patch('file_manager.VideoDigestGenerator'):
                
                mock_settings_instance = MagicMock()
                mock_settings.return_value = mock_settings_instance
                mock_settings_instance.value.return_value = None
                
                try:
                    from file_manager import FileManagerWidget
                    
                    # UIの初期化をスキップ
                    with patch.object(FileManagerWidget, 'init_ui'):
                        with patch.object(FileManagerWidget, 'setup_models'):
                            with patch.object(FileManagerWidget, 'connect_signals'):
                                with patch.object(FileManagerWidget, 'setup_context_menus'):
                                    with patch.object(FileManagerWidget, 'setup_custom_delegate'):
                                        with patch.object(FileManagerWidget, 'apply_settings'):
                                            widget = FileManagerWidget()
                    
                    # 期待される列キーが全て存在することを確認
                    expected_keys = [
                        "name", "size", "type", "modified", "permissions", 
                        "created", "attributes", "extension", "owner", "group"
                    ]
                    
                    for key in expected_keys:
                        assert key in widget.visible_columns, f"Missing key: {key}"
                        assert isinstance(widget.visible_columns[key], bool), f"Key {key} is not boolean"
                    
                    # 名前列は常にTrueであることを確認
                    assert widget.visible_columns["name"] is True
                    
                except Exception as e:
                    pytest.fail(f"Column structure test failed: {e}")

def test_load_settings_method():
    """load_settingsメソッドのテスト"""
    with patch('PySide6.QtCore.QSettings') as mock_settings:
        with patch('PySide6.QtWidgets.QApplication'):
            with patch('file_manager.VideoDigestGenerator'):
                
                mock_settings_instance = MagicMock()
                mock_settings.return_value = mock_settings_instance
                
                # カスタム設定値
                custom_settings = {
                    "show_permissions": True,
                    "show_created": True,
                    "view_mode": "detail",
                    "show_hidden": True
                }
                
                def mock_value(key, default_value=None, type=None):
                    return custom_settings.get(key, default_value)
                
                mock_settings_instance.value.side_effect = mock_value
                
                try:
                    from file_manager import FileManagerWidget
                    
                    # UIの初期化をスキップ
                    with patch.object(FileManagerWidget, 'init_ui'):
                        with patch.object(FileManagerWidget, 'setup_models'):
                            with patch.object(FileManagerWidget, 'connect_signals'):
                                with patch.object(FileManagerWidget, 'setup_context_menus'):
                                    with patch.object(FileManagerWidget, 'setup_custom_delegate'):
                                        with patch.object(FileManagerWidget, 'apply_settings'):
                                            widget = FileManagerWidget()
                    
                    # 設定が正しく読み込まれているかテスト
                    assert widget.visible_columns["permissions"] is True
                    assert widget.visible_columns["created"] is True
                    assert widget.view_mode == "detail"
                    assert widget.show_hidden is True
                    
                except Exception as e:
                    pytest.fail(f"Load settings test failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
