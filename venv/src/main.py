#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUIファイラーアプリケーション - メインエントリーポイント
"""

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt, QDir
from PySide6.QtGui import QIcon

from file_manager import FileManagerWidget


class MainWindow(QMainWindow):
    """メインウィンドウクラス"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GUIファイラー")
        self.setGeometry(100, 100, 1200, 800)
        
        # アイコン設定（将来実装）
        # self.setWindowIcon(QIcon("assets/icons/app_icon.png"))
        
        # セントラルウィジェットの設定
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # レイアウト設定
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # ファイルマネージャーウィジェットの作成
        self.file_manager = FileManagerWidget()
        layout.addWidget(self.file_manager)
        
        # メニューバーとツールバーの設定（将来実装）
        self._setup_menu_bar()
        self._setup_tool_bar()
        
        # ステータスバーの設定
        self.statusBar().showMessage("準備完了")
    
    def _setup_menu_bar(self):
        """メニューバーの設定"""
        menubar = self.menuBar()
        
        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル(&F)")
        
        # 編集メニュー
        edit_menu = menubar.addMenu("編集(&E)")
        
        # 表示メニュー
        view_menu = menubar.addMenu("表示(&V)")
        
        # ヘルプメニュー
        help_menu = menubar.addMenu("ヘルプ(&H)")
    
    def _setup_tool_bar(self):
        """ツールバーの設定"""
        toolbar = self.addToolBar("メインツールバー")
        toolbar.setMovable(False)
        
        # ツールバーボタン（将来実装）
        # toolbar.addAction("上へ", self.file_manager.navigate_up)
        # toolbar.addAction("更新", self.file_manager.refresh)


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    app.setApplicationName("GUIファイラー")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("FileManager")
    
    # アプリケーションスタイルの設定
    app.setStyle('Fusion')  # クロスプラットフォーム対応のスタイル
    
    # メインウィンドウの作成と表示
    window = MainWindow()
    window.show()
    
    # イベントループの開始
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
