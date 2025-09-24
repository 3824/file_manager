#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定反映のテストプログラム
"""

import sys
import os
import tempfile
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, QTimer

# srcディレクトリを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from file_manager import FileManagerWidget

def test_settings_reflection():
    """設定反映のテスト"""
    app = QApplication(sys.argv)
    
    # 一時設定ファイルを使用
    with tempfile.NamedTemporaryFile(suffix='.ini', delete=False) as f:
        settings_file = f.name
    
    try:
        # カスタム設定で初期化
        original_qsettings_init = QSettings.__init__
        def custom_qsettings_init(self, *args, **kwargs):
            if len(args) == 0:
                # デフォルトコンストラクタの場合、一時ファイルを使用
                original_qsettings_init(self, settings_file, QSettings.IniFormat)
            else:
                original_qsettings_init(self, *args, **kwargs)
        
        QSettings.__init__ = custom_qsettings_init
        
        # FileManagerWidgetを作成
        widget = FileManagerWidget()
        widget.show()
        
        print("=== 初期設定 ===")
        print(f"visible_columns: {widget.visible_columns}")
        print(f"view_mode: {widget.view_mode}")
        
        # 詳細表示に切り替え
        if widget.view_mode != "detail":
            print("詳細表示に切り替え中...")
            widget.view_mode_combo.setCurrentIndex(2)
            widget.change_view_mode(2)
            app.processEvents()  # UI更新を待つ
        
        print("\n=== 設定画面を開く前の確認 ===")
        if hasattr(widget, 'list_view') and hasattr(widget.list_view, 'header'):
            header = widget.list_view.header()
            print("現在の列表示状態:")
            columns = ["name", "size", "type", "modified", "permissions", "created", "attributes", "extension", "owner", "group"]
            for i, col_name in enumerate(columns):
                if i < header.count():
                    hidden = header.isSectionHidden(i)
                    print(f"  列{i}({col_name}): {'非表示' if hidden else '表示'}")
        
        # テスト用タイマーを設定
        def perform_test():
            print("\n=== 設定画面テスト開始 ===")
            
            # 設定画面を開く
            try:
                widget.show_settings()
                print("設定画面が呼び出されました")
                
                # 設定反映後の確認
                print("\n=== 設定反映後の確認 ===")
                print(f"visible_columns: {widget.visible_columns}")
                
                if hasattr(widget, 'list_view') and hasattr(widget.list_view, 'header'):
                    header = widget.list_view.header()
                    print("設定反映後の列表示状態:")
                    columns = ["name", "size", "type", "modified", "permissions", "created", "attributes", "extension", "owner", "group"]
                    for i, col_name in enumerate(columns):
                        if i < header.count():
                            hidden = header.isSectionHidden(i)
                            expected_visible = widget.visible_columns.get(col_name, False)
                            status = "✓" if (not hidden) == expected_visible else "✗"
                            print(f"  {status} 列{i}({col_name}): {'非表示' if hidden else '表示'} (期待: {'表示' if expected_visible else '非表示'})")
                
                # アプリケーション終了
                QTimer.singleShot(1000, app.quit)
                
            except Exception as e:
                print(f"テスト中にエラーが発生: {e}")
                QTimer.singleShot(500, app.quit)
        
        # 2秒後にテスト実行
        QTimer.singleShot(2000, perform_test)
        
        # アプリケーション実行
        app.exec()
        
    finally:
        # クリーンアップ
        if os.path.exists(settings_file):
            os.unlink(settings_file)

if __name__ == "__main__":
    test_settings_reflection()
