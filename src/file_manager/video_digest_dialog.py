
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画ダイジェスト表示ダイアログ
"""

import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QWidget, QGridLayout, QFrame,
    QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QPixmap, QFont

from .video_digest import VideoDigestWorker


class VideoDigestDialog(QDialog):
    """動画ダイジェスト表示ダイアログ"""
    
    def __init__(self, video_path, parent=None):
        real_parent = parent if (parent is not None and hasattr(parent, 'window')) else None
        super().__init__(real_parent)
        self.video_path = video_path
        self.settings = QSettings("FileManager", "VideoDigest")
        self.worker = None
        
        # 設定値を読み込み
        self.max_thumbnails = self.settings.value("max_thumbnails", 6, type=int)
        self.thumbnail_size = (
            self.settings.value("thumbnail_width", 160, type=int),
            self.settings.value("thumbnail_height", 90, type=int)
        )
        
        self.init_ui()
        self.generate_digest()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle(f"動画ダイジェスト - {os.path.basename(self.video_path)}")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # ファイル情報表示
        self.create_file_info_section(layout)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        # サムネイル表示エリア
        self.create_thumbnail_section(layout)
        
        # ボタンエリア
        self.create_button_section(layout)
    
    def create_file_info_section(self, parent_layout):
        """ファイル情報表示セクションを作成"""
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 10, 10, 10)
        
        # ファイル名
        filename_label = QLabel(f"ファイル名: {os.path.basename(self.video_path)}")
        filename_label.setFont(QFont("Arial", 10, QFont.Bold))
        info_layout.addWidget(filename_label)
        
        # ファイルパス
        path_label = QLabel(f"パス: {self.video_path}")
        path_label.setWordWrap(True)
        info_layout.addWidget(path_label)
        
        # ファイルサイズ
        try:
            file_size = os.path.getsize(self.video_path)
            size_mb = file_size / (1024 * 1024)
            size_label = QLabel(f"サイズ: {size_mb:.2f} MB")
            info_layout.addWidget(size_label)
        except:
            pass
        
        parent_layout.addWidget(info_frame)
    
    def create_thumbnail_section(self, parent_layout):
        """サムネイル表示セクションを作成"""
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # サムネイルコンテナ
        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QGridLayout(self.thumbnail_container)
        self.thumbnail_layout.setSpacing(10)
        
        scroll_area.setWidget(self.thumbnail_container)
        parent_layout.addWidget(scroll_area)
        
        # 初期メッセージ
        self.initial_label = QLabel("ダイジェストを生成中...")
        self.initial_label.setAlignment(Qt.AlignCenter)
        self.initial_label.setStyleSheet("color: gray; font-size: 14px;")
        self.thumbnail_layout.addWidget(self.initial_label, 0, 0)
    
    def create_button_section(self, parent_layout):
        """ボタンセクションを作成"""
        button_layout = QHBoxLayout()
        
        # 再生成ボタン
        self.regenerate_button = QPushButton("再生成")
        self.regenerate_button.clicked.connect(self.regenerate_digest)
        self.regenerate_button.setEnabled(False)
        button_layout.addWidget(self.regenerate_button)
        
        button_layout.addStretch()
        
        # 閉じるボタン
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        parent_layout.addLayout(button_layout)
    
    def generate_digest(self):
        """ダイジェストを生成"""
        # プログレスバーを表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 再生成ボタンを無効化
        self.regenerate_button.setEnabled(False)
        
        # ワーカースレッドを作成して実行
        self.worker = VideoDigestWorker(
            self.video_path, 
            self.max_thumbnails, 
            self.thumbnail_size
        )
        
        # シグナルを接続
        self.worker.digest_generated.connect(self.on_digest_generated)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.finished.connect(self.on_worker_finished)
        
        # スレッドを開始
        self.worker.start()
    
    def regenerate_digest(self):
        """ダイジェストを再生成"""
        # 既存のサムネイルをクリア
        self.clear_thumbnails()
        
        # ダイジェストを再生成
        self.generate_digest()
    
    def clear_thumbnails(self):
        """サムネイルをクリア"""
        # レイアウトからすべてのウィジェットを削除
        while self.thumbnail_layout.count():
            child = self.thumbnail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # 初期メッセージを表示
        self.initial_label = QLabel("ダイジェストを生成中...")
        self.initial_label.setAlignment(Qt.AlignCenter)
        self.initial_label.setStyleSheet("color: gray; font-size: 14px;")
        self.thumbnail_layout.addWidget(self.initial_label, 0, 0)
    
    def on_digest_generated(self, video_path, thumbnails):
        """ダイジェスト生成完了時の処理"""
        # 初期メッセージを削除
        if hasattr(self, 'initial_label') and self.initial_label:
            self.initial_label.deleteLater()
            self.initial_label = None
        
        # サムネイルを表示
        self.display_thumbnails(thumbnails)
        
        # 再生成ボタンを有効化
        self.regenerate_button.setEnabled(True)
    
    def display_thumbnails(self, thumbnails):
        """サムネイルを表示"""
        if not thumbnails:
            no_thumbnails_label = QLabel("サムネイルを生成できませんでした")
            no_thumbnails_label.setAlignment(Qt.AlignCenter)
            no_thumbnails_label.setStyleSheet("color: red; font-size: 14px;")
            self.thumbnail_layout.addWidget(no_thumbnails_label, 0, 0)
            return
        
        # グリッドレイアウトでサムネイルを配置
        cols = 3  # 1行に3個
        for i, thumbnail in enumerate(thumbnails):
            row = i // cols
            col = i % cols
            
            # サムネイルラベルを作成
            thumbnail_label = QLabel()
            thumbnail_label.setPixmap(thumbnail)
            thumbnail_label.setAlignment(Qt.AlignCenter)
            thumbnail_label.setStyleSheet("border: 1px solid gray;")
            thumbnail_label.setScaledContents(True)
            thumbnail_label.setFixedSize(self.thumbnail_size[0] + 20, self.thumbnail_size[1] + 20)
            
            # フレーム番号を表示
            frame_info = QLabel(f"フレーム {i + 1}")
            frame_info.setAlignment(Qt.AlignCenter)
            frame_info.setStyleSheet("font-size: 10px; color: gray;")
            
            # サムネイルとフレーム情報を縦に配置
            thumbnail_widget = QWidget()
            thumbnail_widget_layout = QVBoxLayout(thumbnail_widget)
            thumbnail_widget_layout.setContentsMargins(5, 5, 5, 5)
            thumbnail_widget_layout.setSpacing(5)
            thumbnail_widget_layout.addWidget(thumbnail_label)
            thumbnail_widget_layout.addWidget(frame_info)
            
            self.thumbnail_layout.addWidget(thumbnail_widget, row, col)
    
    def on_progress_updated(self, progress):
        """進捗更新時の処理"""
        self.progress_bar.setValue(progress)
    
    def on_error_occurred(self, error_message):
        """エラー発生時の処理"""
        QMessageBox.warning(self, "エラー", error_message)
        
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # 再生成ボタンを有効化
        self.regenerate_button.setEnabled(True)
    
    def on_worker_finished(self):
        """ワーカースレッド終了時の処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # ワーカースレッドをクリーンアップ
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
    
    def closeEvent(self, event):
        """ダイアログが閉じられる時の処理"""
        # ワーカースレッドが実行中の場合は停止
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)  # 3秒でタイムアウト
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(3000)
        
        super().closeEvent(event)
