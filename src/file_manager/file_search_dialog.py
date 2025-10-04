#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル検索ダイアログ
"""

import os
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QWidget, QGridLayout, QFrame,
    QMessageBox, QSizePolicy, QCheckBox, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QSlider, QSpinBox, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal
from PySide6.QtGui import QPixmap, QFont, QIcon

from .file_search import FileSearchWorker, IndexUpdateWorker, FileSearchIndex


class FileSearchDialog(QDialog):
    """ファイル検索ダイアログ"""
    
    def __init__(self, parent=None, *, current_path=None, index_db_path=None):
        super().__init__(parent)
        self.current_path = os.fspath(current_path) if current_path else None
        self.index_db_path = index_db_path
        self.search_index = FileSearchIndex(index_db_path=index_db_path)
        self.search_worker = None
        self.index_worker = None
        self.settings = QSettings("FileManager", "FileSearch")

        # 設定値を読み込み
        self.search_limit = self.settings.value("search_limit", 100, type=int)
        self.default_search_type = self.settings.value("default_search_type", "name")
        default_scope_seed = "current" if self.current_path and os.path.isdir(self.current_path) else "all"
        self.default_scope = self.settings.value("default_scope", default_scope_seed)
        if self.default_scope == "current" and not (self.current_path and os.path.isdir(self.current_path)):
            self.default_scope = "all"

        self.init_ui()
        self.load_index_stats()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("ファイル検索")
        self.setModal(True)
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # ヘッダー情報
        self.create_header_section(layout)
        
        # 検索設定エリア
        self.create_search_section(layout)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        # 検索結果エリア
        self.create_results_section(layout)
        
        # ボタンエリア
        self.create_button_section(layout)
    
    def create_header_section(self, parent_layout):
        """ヘッダーセクションを作成"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        # タイトル
        title_label = QLabel("ファイル検索")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)
        
        # インデックス統計情報
        self.stats_label = QLabel("インデックス統計を読み込み中...")
        self.stats_label.setStyleSheet("color: gray;")
        header_layout.addWidget(self.stats_label)
        
        parent_layout.addWidget(header_frame)
    
    def create_search_section(self, parent_layout):
        """検索設定セクションを作成"""
        search_frame = QFrame()
        search_frame.setFrameStyle(QFrame.StyledPanel)
        search_layout = QVBoxLayout(search_frame)
        search_layout.setContentsMargins(10, 10, 10, 10)

        # 検索入力エリア
        input_layout = QHBoxLayout()

        # 検索タイプ選択
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["ファイル名", "拡張子", "パス", "サイズ範囲"])
        self.search_type_combo.setCurrentText(self.default_search_type)
        self.search_type_combo.currentTextChanged.connect(self.on_search_type_changed)

        input_layout.addWidget(QLabel("検索タイプ:"))
        input_layout.addWidget(self.search_type_combo)

        # 検索クエリ入力
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索キーワードを入力してください...")
        self.search_input.returnPressed.connect(self.start_search)
        input_layout.addWidget(QLabel("検索キーワード:"))
        input_layout.addWidget(self.search_input)

        # 検索ボタン
        self.search_button = QPushButton("検索")
        self.search_button.clicked.connect(self.start_search)
        input_layout.addWidget(self.search_button)

        search_layout.addLayout(input_layout)

        # 検索オプション
        options_layout = QHBoxLayout()

        # 結果数制限
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 1000)
        self.limit_spin.setValue(self.search_limit)
        self.limit_spin.setSuffix(" 件")

        options_layout.addWidget(QLabel("結果数制限:"))
        options_layout.addWidget(self.limit_spin)

        # 検索範囲選択
        self.scope_combo = QComboBox()
        if self.current_path and os.path.isdir(self.current_path):
            self.scope_combo.addItem("選択フォルダ内", userData="current")
        self.scope_combo.addItem("全インデックス", userData="all")
        scope_index = self.scope_combo.findData(self.default_scope)
        if scope_index < 0:
            scope_index = self.scope_combo.findData("all")
        if scope_index >= 0:
            self.scope_combo.setCurrentIndex(scope_index)
        options_layout.addWidget(QLabel("検索範囲:"))
        options_layout.addWidget(self.scope_combo)
        options_layout.addStretch()

        # インデックス更新ボタン
        self.update_index_button = QPushButton("インデックス更新")
        self.update_index_button.clicked.connect(self.start_index_update)
        options_layout.addWidget(self.update_index_button)

        search_layout.addLayout(options_layout)

        parent_layout.addWidget(search_frame)
    
    def create_results_section(self, parent_layout):
        """検索結果セクションを作成"""
        results_frame = QFrame()
        results_frame.setFrameStyle(QFrame.StyledPanel)
        results_layout = QVBoxLayout(results_frame)
        results_layout.setContentsMargins(10, 10, 10, 10)
        
        # 結果タイトル
        self.results_title_label = QLabel("検索結果")
        self.results_title_label.setFont(QFont("Arial", 10, QFont.Bold))
        results_layout.addWidget(self.results_title_label)
        
        # 結果テーブル
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["ファイル名", "パス", "サイズ", "更新日時", "種類"])
        
        # テーブルの設定
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ファイル名
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # パス
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # サイズ
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 更新日時
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 種類
        
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.doubleClicked.connect(self.on_result_double_clicked)
        
        results_layout.addWidget(self.results_table)
        
        parent_layout.addWidget(results_frame)
    
    def create_button_section(self, parent_layout):
        """ボタンセクションを作成"""
        button_layout = QHBoxLayout()
        
        # フォルダを開くボタン
        self.open_folder_button = QPushButton("フォルダを開く")
        self.open_folder_button.clicked.connect(self.open_selected_folder)
        self.open_folder_button.setEnabled(False)
        button_layout.addWidget(self.open_folder_button)
        
        # ファイルを開くボタン
        self.open_file_button = QPushButton("ファイルを開く")
        self.open_file_button.clicked.connect(self.open_selected_file)
        self.open_file_button.setEnabled(False)
        button_layout.addWidget(self.open_file_button)
        
        button_layout.addStretch()
        
        # 閉じるボタン
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        parent_layout.addLayout(button_layout)
    
    def load_index_stats(self):
        """インデックス統計情報を読み込み"""
        try:
            stats = self.search_index.get_index_stats()
            if stats:
                last_timestamp = stats.get('last_update')
                if last_timestamp:
                    last_update = datetime.fromtimestamp(last_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    last_update = "未更新"
                self.stats_label.setText(
                    f"インデックス済みファイル: {stats['total_files']}件, "
                    f"フォルダ: {stats['total_directories']}件, "
                    f"最終更新: {last_update}"
                )
            else:
                self.stats_label.setText("インデックスが見つかりません")
        except Exception as e:
            self.stats_label.setText(f"統計情報読み込みエラー: {str(e)}")
    
    def on_search_type_changed(self, text):
        """検索タイプが変更された時の処理"""
        if text == "サイズ範囲":
            self.search_input.setPlaceholderText("例: 1000000-5000000 (バイト単位)")
        elif text == "拡張子":
            self.search_input.setPlaceholderText("例: .mp4, .jpg, .pdf")
        elif text == "パス":
            self.search_input.setPlaceholderText("パスの一部を入力してください...")
        else:
            self.search_input.setPlaceholderText("ファイル名の一部を入力してください...")
    
    def start_search(self):
        """検索を開始"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "警告", "検索キーワードを入力してください。")
            return

        # 検索タイプを取得
        search_type_map = {
            "ファイル名": "name",
            "拡張子": "extension",
            "パス": "path",
            "サイズ範囲": "size_range"
        }
        search_type = search_type_map.get(self.search_type_combo.currentText(), "name")

        scope_choice = getattr(self.scope_combo, 'currentData', lambda: 'all')()
        scope_path = self.current_path if scope_choice == 'current' else None

        # 設定を保存
        self.settings.setValue("search_limit", self.limit_spin.value())
        if scope_choice:
            self.settings.setValue("default_scope", scope_choice)
        self.settings.sync()

        # プログレスバーを表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # ボタンを無効化
        self.search_button.setEnabled(False)
        self.update_index_button.setEnabled(False)

        # 結果テーブルをクリア
        self.results_table.setRowCount(0)

        # ワーカースレッドを作成して実行
        self.search_worker = FileSearchWorker(
            query,
            search_type,
            self.limit_spin.value(),
            scope_path=scope_path,
            index_db_path=self.index_db_path,
        )

        # シグナルを接続
        self.search_worker.search_completed.connect(self.on_search_completed)
        self.search_worker.error_occurred.connect(self.on_error_occurred)
        self.search_worker.finished.connect(self.on_search_worker_finished)

        # スレッドを開始
        self.search_worker.start()
    
    def start_index_update(self):
        """インデックス更新を開始"""
        # プログレスバーを表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # ボタンを無効化
        self.search_button.setEnabled(False)
        self.update_index_button.setEnabled(False)

        target_directory = self.current_path if self.current_path and os.path.isdir(self.current_path) else os.path.expanduser("~")

        # ワーカースレッドを作成して実行
        self.index_worker = IndexUpdateWorker(target_directory, index_db_path=self.index_db_path)

        # シグナルを接続
        self.index_worker.index_updated.connect(self.on_index_updated)
        self.index_worker.progress_updated.connect(self.on_progress_updated)
        self.index_worker.error_occurred.connect(self.on_error_occurred)
        self.index_worker.finished.connect(self.on_index_worker_finished)

        # スレッドを開始
        self.index_worker.start()
    
    def on_search_completed(self, results):
        """検索完了時の処理"""
        self.display_search_results(results)
    
    def display_search_results(self, results):
        """検索結果を表示"""
        self.results_table.setRowCount(len(results))
        
        for row, file_info in enumerate(results):
            # ファイル名
            name_item = QTableWidgetItem(file_info['name'])
            self.results_table.setItem(row, 0, name_item)
            
            # パス
            path_item = QTableWidgetItem(file_info['path'])
            self.results_table.setItem(row, 1, path_item)
            
            # サイズ
            if file_info['is_directory']:
                size_text = "フォルダ"
            else:
                size_mb = file_info['size'] / (1024 * 1024)
                size_text = f"{size_mb:.2f} MB"
            size_item = QTableWidgetItem(size_text)
            size_item.setData(Qt.UserRole, file_info['size'])  # ソート用
            self.results_table.setItem(row, 2, size_item)
            
            # 更新日時
            mod_time = datetime.fromtimestamp(file_info['modified_time'])
            time_text = mod_time.strftime("%Y-%m-%d %H:%M:%S")
            time_item = QTableWidgetItem(time_text)
            time_item.setData(Qt.UserRole, file_info['modified_time'])  # ソート用
            self.results_table.setItem(row, 3, time_item)
            
            # 種類
            if file_info['is_directory']:
                type_text = "フォルダ"
            else:
                ext = file_info.get('extension', '')
                type_text = ext.upper() if ext else "ファイル"
            type_item = QTableWidgetItem(type_text)
            self.results_table.setItem(row, 4, type_item)
        
        # 結果タイトルを更新
        self.results_title_label.setText(f"検索結果 ({len(results)}件)")
        
        # ボタンを有効化
        self.open_folder_button.setEnabled(len(results) > 0)
        self.open_file_button.setEnabled(len(results) > 0)
    
    def on_index_updated(self, indexed_count):
        """インデックス更新完了時の処理"""
        QMessageBox.information(self, "完了", f"{indexed_count}個のファイルをインデックスしました。")
        self.load_index_stats()
    
    def on_progress_updated(self, progress):
        """進捗更新時の処理"""
        self.progress_bar.setValue(progress)
    
    def on_error_occurred(self, error_message):
        """エラー発生時の処理"""
        QMessageBox.warning(self, "エラー", error_message)
    
    def on_search_worker_finished(self):
        """検索ワーカースレッド終了時の処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # ボタンを有効化
        self.search_button.setEnabled(True)
        self.update_index_button.setEnabled(True)
        
        # ワーカースレッドをクリーンアップ
        if self.search_worker:
            self.search_worker.deleteLater()
            self.search_worker = None
    
    def on_index_worker_finished(self):
        """インデックス更新ワーカースレッド終了時の処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # ボタンを有効化
        self.search_button.setEnabled(True)
        self.update_index_button.setEnabled(True)
        
        # ワーカースレッドをクリーンアップ
        if self.index_worker:
            self.index_worker.deleteLater()
            self.index_worker = None
    
    def on_result_double_clicked(self, index):
        """検索結果のダブルクリック時の処理"""
        if index.isValid():
            row = index.row()
            path_item = self.results_table.item(row, 1)
            if path_item:
                file_path = path_item.text()
                self.open_file_or_folder(file_path)
    
    def open_selected_file(self):
        """選択されたファイルを開く"""
        current_row = self.results_table.currentRow()
        if current_row >= 0:
            path_item = self.results_table.item(current_row, 1)
            if path_item:
                file_path = path_item.text()
                self.open_file_or_folder(file_path)
    
    def open_selected_folder(self):
        """選択されたファイルのフォルダを開く"""
        current_row = self.results_table.currentRow()
        if current_row >= 0:
            path_item = self.results_table.item(current_row, 1)
            if path_item:
                file_path = path_item.text()
                folder_path = os.path.dirname(file_path)
                self.open_file_or_folder(folder_path)
    
    def open_file_or_folder(self, path):
        """ファイルまたはフォルダを開く"""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした: {str(e)}")
    
    def closeEvent(self, event):
        """ダイアログが閉じられる時の処理"""
        # ワーカースレッドが実行中の場合は停止
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.quit()
            self.search_worker.wait(3000)
            if self.search_worker.isRunning():
                self.search_worker.terminate()
                self.search_worker.wait(3000)
        
        if self.index_worker and self.index_worker.isRunning():
            self.index_worker.quit()
            self.index_worker.wait(3000)
            if self.index_worker.isRunning():
                self.index_worker.terminate()
                self.index_worker.wait(3000)
        
        super().closeEvent(event)
