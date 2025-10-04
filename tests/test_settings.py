#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイルマネージャーの設定機能のテスト
"""

import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, QDir
from PySide6.QtTest import QTest

from file_manager import FileManagerWidget


class TestFileManagerSettings:
    """FileManagerWidgetの設定機能のテストクラス"""
    
    @pytest.fixture
    def app(self):
        """QApplicationのフィクスチャ"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        yield app
        # テスト後のクリーンアップは不要（QApplicationは再利用）
    
    @pytest.fixture
    def temp_settings_dir(self):
        """一時的な設定ディレクトリのフィクスチャ"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    # pytest-qtの標準qtbotフィクスチャを利用するため、独自qtbotフィクスチャは削除
    
    def test_default_settings_initialization(self, qtbot, temp_settings_dir):
        """デフォルト設定での初期化テスト"""
        # 設定ファイルを一時ディレクトリに配置
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # デフォルト値を返すように設定
            def side_effect(key, default_value=None, type=None):
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
                    "color_hidden": "#808080",
                    "color_readonly": "#0000FF",
                    "color_system": "#FF0000",
                    "color_normal": "#000000",
                    "last_path": ""
                }
                return defaults.get(key, default_value)
            
            mock_settings_instance.value.side_effect = side_effect
            
            # FileManagerWidgetを作成
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # デフォルト設定の確認
            assert widget.visible_columns["name"] is True
            assert widget.visible_columns["size"] is True
            assert widget.visible_columns["type"] is True
            assert widget.visible_columns["modified"] is True
            assert widget.visible_columns["permissions"] is False
            assert widget.visible_columns["created"] is False
            assert widget.visible_columns["attributes"] is False
            assert widget.visible_columns["extension"] is False
            assert widget.visible_columns["owner"] is False
            assert widget.visible_columns["group"] is False
            
            assert widget.view_mode == "list"
            assert widget.show_hidden is False
            
            # 色設定の確認
            assert widget.attribute_colors["hidden"] == "#808080"
            assert widget.attribute_colors["readonly"] == "#0000FF"
            assert widget.attribute_colors["system"] == "#FF0000"
            assert widget.attribute_colors["normal"] == "#000000"
    
    def test_load_custom_settings(self, qtbot, temp_settings_dir):
        """カスタム設定の読み込みテスト"""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # カスタム設定値を返すように設定
            def side_effect(key, default_value=None, type=None):
                custom_settings = {
                    "show_size": False,
                    "show_type": False,
                    "show_modified": True,
                    "show_permissions": True,
                    "show_created": True,
                    "show_attributes": True,
                    "show_extension": True,
                    "show_owner": True,
                    "show_group": True,
                    "view_mode": "detail",
                    "show_hidden": True,
                    "color_hidden": "#FF0000",
                    "color_readonly": "#00FF00",
                    "color_system": "#0000FF",
                    "color_normal": "#FFFF00",
                    "last_path": "/test/path"
                }
                return custom_settings.get(key, default_value)
            
            mock_settings_instance.value.side_effect = side_effect
            
            # FileManagerWidgetを作成
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # カスタム設定の確認
            assert widget.visible_columns["size"] is False
            assert widget.visible_columns["type"] is False
            assert widget.visible_columns["permissions"] is True
            assert widget.visible_columns["created"] is True
            assert widget.visible_columns["attributes"] is True
            assert widget.visible_columns["extension"] is True
            assert widget.visible_columns["owner"] is True
            assert widget.visible_columns["group"] is True
            
            assert widget.view_mode == "detail"
            assert widget.show_hidden is True
            
            # 色設定の確認
            assert widget.attribute_colors["hidden"] == "#FF0000"
            assert widget.attribute_colors["readonly"] == "#00FF00"
            assert widget.attribute_colors["system"] == "#0000FF"
            assert widget.attribute_colors["normal"] == "#FFFF00"
    
    def test_save_settings(self, qtbot, temp_settings_dir):
        """設定保存のテスト"""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # デフォルト値を返すように設定
            mock_settings_instance.value.return_value = None
            
            # FileManagerWidgetを作成
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # 設定を変更
            widget.visible_columns["permissions"] = True
            widget.visible_columns["created"] = True
            widget.view_mode = "detail"
            widget.show_hidden = True
            widget.attribute_colors["hidden"] = "#123456"
            
            # 設定を保存
            widget.save_settings()
            
            # 保存が呼ばれたことを確認
            mock_settings_instance.setValue.assert_any_call("show_permissions", True)
            mock_settings_instance.setValue.assert_any_call("show_created", True)
            mock_settings_instance.setValue.assert_any_call("view_mode", "detail")
            mock_settings_instance.setValue.assert_any_call("show_hidden", True)
            mock_settings_instance.setValue.assert_any_call("color_hidden", "#123456")
            mock_settings_instance.sync.assert_called_once()
    
    def test_apply_settings(self, qtbot, temp_settings_dir):
        """設定適用のテスト"""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # デフォルト値を返すように設定
            def side_effect(key, default_value=None, type=None):
                return default_value
            
            mock_settings_instance.value.side_effect = side_effect
            
            # FileManagerWidgetを作成
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # 設定を変更
            mock_settings_instance.value.side_effect = lambda key, default_value=None, type=None: {
                "show_permissions": True,
                "show_created": True,
                "view_mode": "detail",
                "tree_font_family": "Arial",
                "tree_font_size": 12,
                "list_font_family": "Arial",
                "list_font_size": 10
            }.get(key, default_value)
            
            # 設定を適用
            widget.apply_settings()
            
            # 設定が適用されたことを確認
            assert widget.visible_columns["permissions"] is True
            assert widget.visible_columns["created"] is True
            assert widget.view_mode == "detail"
    
    def test_last_path_restoration(self, qtbot, temp_settings_dir):
        """前回パスの復元テスト"""
        test_path = QDir.homePath()
        
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # last_pathを返すように設定
            def side_effect(key, default_value=None, type=None):
                if key == "last_path":
                    return test_path
                return default_value
            
            mock_settings_instance.value.side_effect = side_effect
            
            # os.path.isdirをモック
            with patch('os.path.isdir', return_value=True):
                with patch('file_manager.VideoDigestGenerator'):
                    widget = FileManagerWidget()
                    qtbot.addWidget(widget)
                
                # 前回パスが復元されたことを確認
                assert widget.current_path == test_path
    
    def test_settings_error_handling(self, qtbot, temp_settings_dir):
        """設定処理のエラーハンドリングテスト"""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # 設定読み込み時にエラーを発生させる
            mock_settings_instance.value.side_effect = Exception("Settings error")
            
            # FileManagerWidgetを作成（エラーが発生しても正常に初期化されることを確認）
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # デフォルト設定にフォールバックされていることを確認
            assert widget.visible_columns["name"] is True
            assert widget.visible_columns["size"] is True
            assert widget.view_mode == "list"
            assert widget.show_hidden is False
    
    def test_visible_columns_consistency(self, qtbot, temp_settings_dir):
        """表示列設定の整合性テスト"""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # デフォルト値を返すように設定
            mock_settings_instance.value.return_value = None
            
            # FileManagerWidgetを作成
            with patch('file_manager.VideoDigestGenerator'):
                widget = FileManagerWidget()
                qtbot.addWidget(widget)
            
            # 表示列設定の全キーが存在することを確認
            expected_keys = [
                "name", "size", "type", "modified", "permissions", 
                "created", "attributes", "extension", "owner", "group"
            ]
            
            for key in expected_keys:
                assert key in widget.visible_columns
                assert isinstance(widget.visible_columns[key], bool)
            
            # 名前列は常にTrueであることを確認
            assert widget.visible_columns["name"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
