#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同一動画ファイル比較・削除ダイアログ
"""

import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QWidget, QGridLayout, QFrame,
    QMessageBox, QSizePolicy, QCheckBox, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QSlider, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal
from PySide6.QtGui import QPixmap, QFont, QIcon

from duplicate_video_detector import DuplicateVideoDetector, DuplicateVideoWorker
from video_digest_dialog import VideoDigestDialog


class VideoComparisonWidget(QWidget):
    """動画比較ウィジェット"""
    
    # シグナル定義
    selection_changed = Signal()  # 選択状態が変更された時のシグナル
    
    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths
        self.thumbnails = {}
        self.selected_videos = set()  # 選択された動画のパスを保存
        self.checkboxes = {}  # チェックボックスの参照を保存
        
        try:
            self.init_ui()
            self.load_thumbnails()
        except Exception as e:
            print(f"VideoComparisonWidget初期化エラー: {e}")
            # エラーが発生してもウィジェットは表示する
            self.init_ui()
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # タイトル
        title_label = QLabel(f"動画比較 ({len(self.video_paths)}個のファイル)")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title_label)
        
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
        layout.addWidget(scroll_area)
        
        # 初期メッセージ
        self.initial_label = QLabel("サムネイルを読み込み中...")
        self.initial_label.setAlignment(Qt.AlignCenter)
        self.initial_label.setStyleSheet("color: gray; font-size: 14px;")
        self.thumbnail_layout.addWidget(self.initial_label, 0, 0)
    
    def load_thumbnails(self):
        """サムネイルを読み込み"""
        try:
            if not self.video_paths:
                return
            
            # 初期メッセージを削除
            if hasattr(self, 'initial_label') and self.initial_label:
                self.initial_label.deleteLater()
                self.initial_label = None
            
            # 各動画のサムネイルを生成
            for i, video_path in enumerate(self.video_paths):
                try:
                    self.create_video_thumbnail(video_path, i)
                except Exception as e:
                    print(f"サムネイル作成エラー ({video_path}): {e}")
                    # エラーが発生したサムネイルはスキップして続行
        except Exception as e:
            print(f"サムネイル読み込みエラー: {e}")
    
    def create_video_thumbnail(self, video_path, index):
        """動画のサムネイルを作成"""
        try:
            # ファイル情報
            file_name = os.path.basename(video_path)
            file_size = os.path.getsize(video_path)
            size_mb = file_size / (1024 * 1024)
            
            # サムネイルウィジェット
            thumbnail_widget = QFrame()
            thumbnail_widget.setFrameStyle(QFrame.StyledPanel)
            thumbnail_widget.setFixedSize(200, 170)  # 高さを少し増やしてチェックボックス用のスペースを確保
            
            layout = QVBoxLayout(thumbnail_widget)
            layout.setContentsMargins(5, 5, 5, 5)
            layout.setSpacing(5)
            
            # チェックボックス（左上に配置）
            checkbox_layout = QHBoxLayout()
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setSpacing(0)
            
            checkbox = QCheckBox()
            checkbox.stateChanged.connect(lambda state, path=video_path: self.on_checkbox_changed(path, state))
            self.checkboxes[video_path] = checkbox  # チェックボックスの参照を保存
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.addStretch()
            
            layout.addLayout(checkbox_layout)
            
            # サムネイル画像（プレースホルダー）
            thumbnail_label = QLabel()
            thumbnail_label.setFixedSize(180, 100)
            thumbnail_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
            thumbnail_label.setAlignment(Qt.AlignCenter)
            thumbnail_label.setText("読み込み中...")
            layout.addWidget(thumbnail_label)
            
            # ファイル情報
            info_label = QLabel(f"{file_name}\n{size_mb:.2f} MB")
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setWordWrap(True)
            info_label.setStyleSheet("font-size: 10px;")
            layout.addWidget(info_label)
            
            # ダイジェスト表示ボタン
            digest_button = QPushButton("詳細表示")
            digest_button.setFixedHeight(20)
            digest_button.clicked.connect(lambda: self.show_digest(video_path))
            layout.addWidget(digest_button)
            
            # グリッドに配置
            row = index // 3
            col = index % 3
            self.thumbnail_layout.addWidget(thumbnail_widget, row, col)
            
            # 非同期でサムネイルを生成
            QTimer.singleShot(100, lambda: self.generate_thumbnail_async(video_path, thumbnail_label))
            
        except Exception as e:
            print(f"サムネイル作成エラー: {e}")
    
    def on_checkbox_changed(self, video_path, state):
        """チェックボックスの状態が変更された時の処理"""
        if state == Qt.Checked:
            self.selected_videos.add(video_path)
        else:
            self.selected_videos.discard(video_path)
        
        # 選択状態が変更されたことを親に通知
        self.selection_changed.emit()
        
        # 親ダイアログのUIを即時更新
        parent = self.parent()
        if parent and hasattr(parent, 'on_video_selection_changed'):
            # 即座に呼び出し、遅延は不要
            parent.on_video_selection_changed()
    
    def get_selected_videos(self):
        """選択された動画のパスリストを取得"""
        return list(self.selected_videos)
    
    def clear_selection(self):
        """選択をクリア"""
        self.selected_videos.clear()
        # 保存されたチェックボックスの参照を使用
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)
        
        # シグナルを発火して選択状態を更新
        self.selection_changed.emit()
        parent = self.parent()
        if parent and hasattr(parent, 'on_video_selection_changed'):
            QTimer.singleShot(0, parent.on_video_selection_changed)
    
    def select_all(self):
        """すべてのファイルを選択"""
        for video_path in self.video_paths:
            self.selected_videos.add(video_path)
            if video_path in self.checkboxes:
                self.checkboxes[video_path].setChecked(True)
        self.selection_changed.emit()
        parent = self.parent()
        if parent and hasattr(parent, 'on_video_selection_changed'):
            # 即座に呼び出し、遅延は不要
            parent.on_video_selection_changed()
    
    def generate_thumbnail_async(self, video_path, thumbnail_label):
        """非同期でサムネイルを生成"""
        try:
            # 簡単なサムネイル生成（実際の実装ではVideoDigestGeneratorを使用）
            from video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
            
            if not OPENCV_AVAILABLE:
                thumbnail_label.setText("OpenCV未インストール")
                return
            
            generator = VideoDigestGenerator()
            generator.generate_digest(video_path, max_thumbnails=1, thumbnail_size=(180, 100))
            
            # シグナルを接続してサムネイルを取得
            def on_digest_generated(path, thumbnails):
                if path == video_path and thumbnails:
                    thumbnail_label.setPixmap(thumbnails[0])
                    thumbnail_label.setText("")
            
            generator.digest_generated.connect(on_digest_generated)
            
        except Exception as e:
            thumbnail_label.setText("エラー")
            print(f"サムネイル生成エラー: {e}")
    
    def show_digest(self, video_path):
        """動画ダイジェストを表示"""
        try:
            dialog = VideoDigestDialog(video_path, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ダイジェストの表示中にエラーが発生しました: {str(e)}")


class DuplicateVideoDialog(QDialog):
    """同一動画ファイル比較・削除ダイアログ"""
    
    def __init__(self, directory_path, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.duplicate_groups = []
        self.selected_files = set()
        self.settings = QSettings("FileManager", "DuplicateVideo")
        self.worker = None
        
        try:
            # 設定値を読み込み
            self.similarity_threshold = self.settings.value("similarity_threshold", 0.8, type=float)
            self.max_thumbnails = self.settings.value("max_thumbnails", 6, type=int)
            
            self.init_ui()
            self.start_detection()
        except Exception as e:
            QMessageBox.critical(self, "初期化エラー", f"ダイアログの初期化中にエラーが発生しました:\n{str(e)}")
            self.close()
    
    def init_ui(self):
        """UIの初期化"""
        try:
            self.setWindowTitle(f"同一動画ファイル検出 - {os.path.basename(self.directory_path)}")
            self.setModal(True)
            self.resize(1200, 800)
            
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)
            
            # ヘッダー情報
            self.create_header_section(layout)
            
            # プログレスバー
            self.progress_bar = QProgressBar()
            self.progress_bar.setVisible(False)
            self.progress_bar.setRange(0, 100)
            layout.addWidget(self.progress_bar)
            
            # メインコンテンツエリア
            self.create_main_content(layout)
            
            # ボタンエリア
            self.create_button_section(layout)
            
        except Exception as e:
            QMessageBox.critical(self, "UI初期化エラー", f"UIの初期化中にエラーが発生しました:\n{str(e)}")
            raise
    
    def create_header_section(self, parent_layout):
        """ヘッダーセクションを作成"""
        # 設定エリアのみをコンパクトに配置
        settings_layout = QHBoxLayout()
        
        # 検出タイプ選択
        detection_label = QLabel("検出タイプ:")
        self.detection_combo = QComboBox()
        self.detection_combo.addItems(["ファイルサイズ", "ファイル名類似性"])
        self.detection_combo.currentTextChanged.connect(self.on_detection_type_changed)
        
        settings_layout.addWidget(detection_label)
        settings_layout.addWidget(self.detection_combo)
        
        # 類似度閾値設定（ファイル名類似性の場合のみ表示）
        self.threshold_label = QLabel("類似度閾値:")
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 100)
        self.threshold_slider.setValue(int(self.similarity_threshold * 100))
        self.threshold_slider.valueChanged.connect(self.on_threshold_changed)
        
        self.threshold_value_label = QLabel(f"{self.similarity_threshold:.2f}")
        self.threshold_value_label.setMinimumWidth(50)
        
        settings_layout.addWidget(self.threshold_label)
        settings_layout.addWidget(self.threshold_slider)
        settings_layout.addWidget(self.threshold_value_label)
        
        # 初期状態では類似度設定を非表示
        self.threshold_label.setVisible(False)
        self.threshold_slider.setVisible(False)
        self.threshold_value_label.setVisible(False)
        
        settings_layout.addStretch()
        
        # 再検出ボタン
        self.redetect_button = QPushButton("再検出")
        self.redetect_button.clicked.connect(self.start_detection)
        self.redetect_button.setEnabled(False)
        settings_layout.addWidget(self.redetect_button)
        
        parent_layout.addLayout(settings_layout)
    
    def create_main_content(self, parent_layout):
        """メインコンテンツエリアを作成"""
        # スプリッター
        splitter = QSplitter(Qt.Horizontal)
        
        # 左ペイン: 重複グループリスト
        self.create_group_list_pane(splitter)
        
        # 右ペイン: 動画比較エリア
        self.create_comparison_pane(splitter)
        
        # スプリッターの比率設定
        splitter.setSizes([300, 900])
        
        parent_layout.addWidget(splitter)
    
    def create_group_list_pane(self, parent_splitter):
        """重複グループリストペインを作成"""
        group_widget = QWidget()
        group_layout = QVBoxLayout(group_widget)
        group_layout.setContentsMargins(5, 5, 5, 5)
        
        # タイトル
        title_label = QLabel("同一サイズの動画グループ")
        title_label.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout.addWidget(title_label)
        
        # グループリスト
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self.on_group_selected)
        group_layout.addWidget(self.group_list)
        
        # 選択されたファイル数表示
        self.selected_count_label = QLabel("選択されたファイル: 0個")
        self.selected_count_label.setStyleSheet("color: blue; font-weight: bold;")
        group_layout.addWidget(self.selected_count_label)
        
        parent_splitter.addWidget(group_widget)
    
    def create_comparison_pane(self, parent_splitter):
        """動画比較ペインを作成"""
        comparison_widget = QWidget()
        comparison_layout = QVBoxLayout(comparison_widget)
        comparison_layout.setContentsMargins(5, 5, 5, 5)
        
        # タイトル
        self.comparison_title_label = QLabel("動画を選択してください")
        self.comparison_title_label.setFont(QFont("Arial", 10, QFont.Bold))
        comparison_layout.addWidget(self.comparison_title_label)
        
        # 比較エリア
        self.comparison_area = QScrollArea()
        self.comparison_area.setWidgetResizable(True)
        self.comparison_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.comparison_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # 初期メッセージ
        initial_message = QLabel("左側のリストから動画グループを選択してください")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setStyleSheet("color: gray; font-size: 14px;")
        self.comparison_area.setWidget(initial_message)
        
        comparison_layout.addWidget(self.comparison_area)
        
        parent_splitter.addWidget(comparison_widget)
    
    def create_button_section(self, parent_layout):
        """ボタンセクションを作成"""
        button_layout = QHBoxLayout()
        
        # 全選択/全解除ボタン
        self.select_all_button = QPushButton("全選択")
        self.select_all_button.clicked.connect(self.select_all_files)
        self.select_all_button.setEnabled(False)
        button_layout.addWidget(self.select_all_button)
        
        self.deselect_all_button = QPushButton("全解除")
        self.deselect_all_button.clicked.connect(self.deselect_all_files)
        self.deselect_all_button.setEnabled(False)
        button_layout.addWidget(self.deselect_all_button)
        
        button_layout.addStretch()
        
        # 削除ボタン
        self.delete_button = QPushButton("選択したファイルをゴミ箱に移動")
        self.delete_button.clicked.connect(self.delete_selected_files)
        self.delete_button.setEnabled(False)
        # 初期状態では無効化されたスタイル
        self.delete_button.setStyleSheet("background-color: #cccccc; color: #666666; font-weight: normal;")
        button_layout.addWidget(self.delete_button)
        
        # 閉じるボタン
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        parent_layout.addLayout(button_layout)
    
    def start_detection(self):
        """重複ファイル検出を開始"""
        try:
            # プログレスバーを表示
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # ボタンを無効化
            self.redetect_button.setEnabled(False)
            self.select_all_button.setEnabled(False)
            self.deselect_all_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            
            # リストをクリア
            self.group_list.clear()
            self.selected_files.clear()
            # 選択数表示をリセット
            self.selected_count_label.setText("選択されたファイル: 0個")
            
            # 検出タイプを取得
            detection_type = "size" if self.detection_combo.currentText() == "ファイルサイズ" else "name"
            
            # 初期メッセージを表示
            initial_message = QLabel()
            initial_message.setAlignment(Qt.AlignCenter)
            initial_message.setStyleSheet("color: gray; font-size: 14px;")
            if detection_type == "size":
                initial_message.setText("同一サイズの動画ファイルを検出中...")
            else:
                initial_message.setText("類似ファイル名の動画ファイルを検出中...")
            self.comparison_area.setWidget(initial_message)
            
            # ワーカースレッドを作成して実行
            self.worker = DuplicateVideoWorker(
                self.directory_path, 
                detection_type, 
                self.similarity_threshold
            )
            
            # シグナルを接続
            self.worker.duplicates_found.connect(self.on_duplicates_found)
            self.worker.progress_updated.connect(self.on_progress_updated)
            self.worker.error_occurred.connect(self.on_error_occurred)
            self.worker.finished.connect(self.on_worker_finished)
            
            # スレッドを開始
            self.worker.start()
            
        except Exception as e:
            QMessageBox.warning(self, "検出開始エラー", f"重複ファイル検出の開始中にエラーが発生しました:\n{str(e)}")
            self.progress_bar.setVisible(False)
            self.redetect_button.setEnabled(True)
    
    def on_duplicates_found(self, duplicate_groups):
        """重複ファイルが見つかった時の処理"""
        self.duplicate_groups = duplicate_groups
        
        if not duplicate_groups:
            no_results_message = QLabel("同一サイズの動画ファイルは見つかりませんでした")
            no_results_message.setAlignment(Qt.AlignCenter)
            no_results_message.setStyleSheet("color: gray; font-size: 14px;")
            self.comparison_area.setWidget(no_results_message)
            return
        
        # グループリストを更新
        self.group_list.clear()
        for i, group in enumerate(duplicate_groups):
            size_mb = group['size'] / (1024 * 1024)
            
            # グループタイプに応じて表示を変更
            if group.get('type') == 'name':
                similarity = group.get('similarity', 0.0)
                item_text = f"グループ {i+1}: {group['count']}個のファイル (類似度: {similarity:.2f}, {size_mb:.2f} MB)"
            else:
                item_text = f"グループ {i+1}: {group['count']}個のファイル ({size_mb:.2f} MB)"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, i)
            self.group_list.addItem(item)
        
        # ボタンを有効化
        self.redetect_button.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.deselect_all_button.setEnabled(True)
    
    def on_group_selected(self, item):
        """グループが選択された時の処理"""
        group_index = item.data(Qt.UserRole)
        if group_index is None:
            return
        
        group = self.duplicate_groups[group_index]
        video_paths = [file['path'] for file in group['files']]
        
        # タイトルを更新
        self.comparison_title_label.setText(f"グループ {group_index + 1}: {len(video_paths)}個の動画")
        
        # 比較ウィジェットを作成
        comparison_widget = VideoComparisonWidget(video_paths, self)
        comparison_widget.selection_changed.connect(self.on_video_selection_changed)
        self.comparison_area.setWidget(comparison_widget)
        
        # 初期状態では削除ボタンを無効化
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("background-color: #cccccc; color: #666666; font-weight: normal;")
        self.selected_count_label.setText("選択されたファイル: 0個")
    
    def on_detection_type_changed(self, text):
        """検出タイプが変更された時の処理"""
        # 類似度設定の表示/非表示を切り替え
        is_name_detection = text == "ファイル名類似性"
        self.threshold_label.setVisible(is_name_detection)
        self.threshold_slider.setVisible(is_name_detection)
        self.threshold_value_label.setVisible(is_name_detection)
    
    def on_threshold_changed(self, value):
        """類似度閾値が変更された時の処理"""
        self.similarity_threshold = value / 100.0
        self.threshold_value_label.setText(f"{self.similarity_threshold:.2f}")
        
        # 設定を保存
        self.settings.setValue("similarity_threshold", self.similarity_threshold)
    
    def on_video_selection_changed(self):
        """動画の選択状態が変更された時の処理"""
        # 現在の比較ウィジェットから選択された動画を取得
        current_widget = self.comparison_area.widget()
        
        if isinstance(current_widget, VideoComparisonWidget):
            selected_videos = current_widget.get_selected_videos()
            selected_count = len(selected_videos)
            
            # UIの更新
            self.selected_count_label.setText(f"選択されたファイル: {selected_count}個")
            
            # 削除ボタンの有効/無効を更新
            button_enabled = selected_count > 0
            self.delete_button.setEnabled(button_enabled)
            
            # ボタンのスタイルも更新（視覚的フィードバック）
            if button_enabled:
                self.delete_button.setStyleSheet("background-color: #ff6b6b; color: white; font-weight: bold;")
            else:
                self.delete_button.setStyleSheet("background-color: #cccccc; color: #666666; font-weight: normal;")
            
            # 強制的にUIを更新
            self.selected_count_label.repaint()
            self.delete_button.repaint()
            self.update()  # ウィジェット全体を更新
    
    
    def select_all_files(self):
        """すべてのファイルを選択"""
        current_widget = self.comparison_area.widget()
        if isinstance(current_widget, VideoComparisonWidget):
            current_widget.select_all()
    
    def deselect_all_files(self):
        """すべてのファイルの選択を解除"""
        current_widget = self.comparison_area.widget()
        if isinstance(current_widget, VideoComparisonWidget):
            current_widget.clear_selection()
    
    
    def delete_selected_files(self):
        """選択されたファイルをゴミ箱に移動"""
        # 現在の比較ウィジェットから選択された動画を取得
        current_widget = self.comparison_area.widget()
        if not isinstance(current_widget, VideoComparisonWidget):
            return
        
        selected_videos = current_widget.get_selected_videos()
        if not selected_videos:
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, "削除確認", 
            f"{len(selected_videos)}個のファイルをゴミ箱に移動しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                moved_count = 0
                for file_path in selected_videos:
                    if os.path.exists(file_path):
                        if self.move_to_trash(file_path):
                            moved_count += 1
                
                QMessageBox.information(self, "移動完了", f"{moved_count}個のファイルをゴミ箱に移動しました。")
                
                # 選択をクリア
                current_widget.clear_selection()
                
                # 削除ボタンの状態をリセット
                self.delete_button.setEnabled(False)
                self.delete_button.setStyleSheet("background-color: #cccccc; color: #666666; font-weight: normal;")
                self.selected_count_label.setText("選択されたファイル: 0個")
                
                # 再検出を実行
                self.start_detection()
                
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"ファイルの移動中にエラーが発生しました: {str(e)}")
    
    def move_to_trash(self, file_path):
        """ファイルをゴミ箱に移動"""
        try:
            if sys.platform == "win32":
                # Windowsの場合
                import winshell
                winshell.delete_file(file_path, no_confirm=True)
                return True
            elif sys.platform == "darwin":
                # macOSの場合
                import send2trash
                send2trash.send2trash(file_path)
                return True
            else:
                # Linuxの場合
                try:
                    import send2trash
                    send2trash.send2trash(file_path)
                    return True
                except ImportError:
                    # send2trashが利用できない場合は通常削除
                    os.remove(file_path)
                    return True
        except Exception as e:
            print(f"ゴミ箱への移動エラー: {e}")
            # フォールバック: 通常削除
            try:
                os.remove(file_path)
                return True
            except Exception as e2:
                print(f"通常削除もエラー: {e2}")
                return False
    
    def on_progress_updated(self, progress):
        """進捗更新時の処理"""
        self.progress_bar.setValue(progress)
    
    def on_error_occurred(self, error_message):
        """エラー発生時の処理"""
        QMessageBox.warning(self, "エラー", error_message)
        
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # ボタンを有効化
        self.redetect_button.setEnabled(True)
    
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
