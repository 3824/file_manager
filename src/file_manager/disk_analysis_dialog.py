#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ディスク使用量分析・円グラフ表示ダイアログ
"""

import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QWidget, QGridLayout, QFrame,
    QMessageBox, QSizePolicy, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QComboBox, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal, QRectF
from PySide6.QtGui import QPixmap, QFont, QIcon, QPainter, QPen, QBrush, QColor

from .disk_analyzer import DiskAnalysisWorker, DiskAnalyzer


class PieChartWidget(QWidget):
    """円グラフウィジェット"""
    
    def __init__(self, data_list=None, parent=None):
        super().__init__(parent)
        self.data_list = data_list or []
        self.selected_index = -1
        self.setMinimumSize(400, 400)
        
        # 色のパレット
        self.colors = [
            QColor("#FF6B6B"), QColor("#4ECDC4"), QColor("#45B7D1"), 
            QColor("#96CEB4"), QColor("#FECA57"), QColor("#FF9FF3"),
            QColor("#54A0FF"), QColor("#5F27CD"), QColor("#00D2D3"),
            QColor("#FF9F43"), QColor("#10AC84"), QColor("#EE5A24"),
            QColor("#0984E3"), QColor("#A29BFE"), QColor("#FD79A8")
        ]
    
    def set_data(self, data_list):
        """データを設定"""
        self.data_list = data_list
        self.selected_index = -1
        self.update()
    
    def paintEvent(self, event):
        """描画イベント"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # ウィジェットのサイズを取得
        width = self.width()
        height = self.height()
        size = min(width, height) - 40  # マージンを考慮
        
        # 円グラフの中心座標
        center_x = width // 2
        center_y = height // 2
        radius = size // 2
        
        # データがない場合は何も描画しない
        if not self.data_list:
            painter.drawText(center_x - 50, center_y, "データがありません")
            return
        
        # 総サイズを計算
        total_size = sum(item['size'] for item in self.data_list)
        if total_size == 0:
            painter.drawText(center_x - 50, center_y, "サイズが0です")
            return
        
        # 円グラフを描画
        current_angle = 0
        for i, item in enumerate(self.data_list):
            # 角度を計算
            angle = int(360 * item['size'] / total_size)
            
            # 色を選択
            color = self.colors[i % len(self.colors)]
            if i == self.selected_index:
                color = color.lighter(120)  # 選択時は明るく
            
            # 扇形を描画
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.black, 2))
            painter.drawPie(
                center_x - radius, center_y - radius, 
                radius * 2, radius * 2, 
                current_angle * 16, angle * 16
            )
            
            current_angle += angle
        
        # 凡例を描画
        self.draw_legend(painter, width, height)
    
    def draw_legend(self, painter, width, height):
        """凡例を描画"""
        legend_x = 20
        legend_y = 20
        legend_width = 200
        legend_height = min(len(self.data_list) * 20 + 20, height - 40)
        
        # 凡例の背景
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(legend_x, legend_y, legend_width, legend_height)
        
        # 凡例のアイテム
        painter.setFont(QFont("Arial", 9))
        for i, item in enumerate(self.data_list):
            item_y = legend_y + 15 + i * 20
            
            # 色の四角形
            color = self.colors[i % len(self.colors)]
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.black, 1))
            painter.drawRect(legend_x + 5, item_y - 8, 12, 12)
            
            # テキスト
            painter.setPen(QPen(Qt.black))
            name = item['name']
            if len(name) > 20:
                name = name[:17] + "..."
            
            size_text = self.format_size(item['size'])
            painter.drawText(legend_x + 25, item_y, f"{name} ({size_text})")
    
    def format_size(self, size_bytes):
        """バイト数を人間が読みやすい形式に変換"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def mousePressEvent(self, event):
        """マウスクリックイベント"""
        if event.button() == Qt.LeftButton:
            # クリック位置から扇形を特定（簡易版）
            click_pos = event.pos()
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            # 円グラフの範囲内かチェック
            dx = click_pos.x() - center_x
            dy = click_pos.y() - center_y
            distance = (dx * dx + dy * dy) ** 0.5
            
            if distance < min(self.width(), self.height()) // 2 - 20:
                # 角度を計算
                import math
                angle = math.atan2(dy, dx)
                if angle < 0:
                    angle += 2 * math.pi
                angle = math.degrees(angle)
                
                # どの扇形に該当するかを計算
                total_size = sum(item['size'] for item in self.data_list)
                current_angle = 0
                
                for i, item in enumerate(self.data_list):
                    item_angle = 360 * item['size'] / total_size
                    if current_angle <= angle < current_angle + item_angle:
                        self.selected_index = i
                        self.update()
                        self.selection_changed.emit(item)
                        break
                    current_angle += item_angle
    
    # シグナル定義
    selection_changed = Signal(dict)  # 選択されたアイテム


class DiskAnalysisDialog(QDialog):
    """ディスク使用量分析ダイアログ"""
    
    def __init__(self, initial_path=None, parent=None):
        super().__init__(parent)
        self.current_path = initial_path or os.path.expanduser("~")
        self.analyzer = DiskAnalyzer()
        self.analysis_worker = None
        self.current_data = []
        self.settings = QSettings("FileManager", "DiskAnalysis")
        
        self.init_ui()
        self.start_analysis()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("ディスク使用量分析")
        self.setModal(True)
        self.resize(1000, 700)
        
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
    
    def create_header_section(self, parent_layout):
        """ヘッダーセクションを作成"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        # タイトル
        title_label = QLabel("ディスク使用量分析")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)
        
        # 現在のパス
        self.path_label = QLabel(f"分析対象: {self.current_path}")
        self.path_label.setWordWrap(True)
        header_layout.addWidget(self.path_label)
        
        # ドライブ選択
        drive_layout = QHBoxLayout()
        drive_layout.addWidget(QLabel("ドライブ選択:"))
        
        self.drive_combo = QComboBox()
        self.setup_drive_combo()
        drive_layout.addWidget(self.drive_combo)
        
        # 分析開始ボタン
        self.analyze_button = QPushButton("分析開始")
        self.analyze_button.clicked.connect(self.start_analysis)
        drive_layout.addWidget(self.analyze_button)
        
        # 戻るボタン
        self.back_button = QPushButton("← 戻る")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)
        drive_layout.addWidget(self.back_button)
        
        header_layout.addLayout(drive_layout)
        parent_layout.addWidget(header_frame)
    
    def setup_drive_combo(self):
        """ドライブ選択コンボボックスを設定"""
        self.drive_combo.clear()
        
        if sys.platform == "win32":
            # Windowsの場合
            import string
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    self.drive_combo.addItem(f"{letter}:", drive_path)
        else:
            # Unix系の場合
            self.drive_combo.addItem("/", "/")
            # ホームディレクトリも追加
            home_path = os.path.expanduser("~")
            self.drive_combo.addItem(f"ホーム ({home_path})", home_path)
        
        # 現在のパスに最も近いドライブを選択
        current_drive = self.get_drive_from_path(self.current_path)
        for i in range(self.drive_combo.count()):
            if self.drive_combo.itemData(i) == current_drive:
                self.drive_combo.setCurrentIndex(i)
                break
    
    def get_drive_from_path(self, path):
        """パスからドライブを取得"""
        if sys.platform == "win32":
            if len(path) >= 2 and path[1] == ':':
                return path[:2] + '\\'
        return os.path.sep  # Unix系ではルートディレクトリ
    
    def create_main_content(self, parent_layout):
        """メインコンテンツエリアを作成"""
        # スプリッター
        splitter = QSplitter(Qt.Horizontal)
        
        # 左ペイン: 円グラフ
        self.create_chart_pane(splitter)
        
        # 右ペイン: 詳細リスト
        self.create_detail_pane(splitter)
        
        # スプリッターの比率設定
        splitter.setSizes([500, 500])
        
        parent_layout.addWidget(splitter)
    
    def create_chart_pane(self, parent_splitter):
        """円グラフペインを作成"""
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        chart_layout.setContentsMargins(5, 5, 5, 5)
        
        # タイトル
        chart_title_label = QLabel("使用量分布")
        chart_title_label.setFont(QFont("Arial", 12, QFont.Bold))
        chart_title_label.setAlignment(Qt.AlignCenter)
        chart_layout.addWidget(chart_title_label)
        
        # 円グラフウィジェット
        self.pie_chart = PieChartWidget()
        self.pie_chart.selection_changed.connect(self.on_chart_item_selected)
        chart_layout.addWidget(self.pie_chart)
        
        parent_splitter.addWidget(chart_widget)
    
    def create_detail_pane(self, parent_splitter):
        """詳細ペインを作成"""
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(5, 5, 5, 5)
        
        # タイトル
        detail_title_label = QLabel("詳細リスト")
        detail_title_label.setFont(QFont("Arial", 12, QFont.Bold))
        detail_layout.addWidget(detail_title_label)
        
        # 詳細リスト
        self.detail_list = QListWidget()
        self.detail_list.itemDoubleClicked.connect(self.on_detail_item_double_clicked)
        detail_layout.addWidget(self.detail_list)
        
        parent_splitter.addWidget(detail_widget)
    
    def create_button_section(self, parent_layout):
        """ボタンセクションを作成"""
        button_layout = QHBoxLayout()
        
        # フォルダを開くボタン
        self.open_folder_button = QPushButton("フォルダを開く")
        self.open_folder_button.clicked.connect(self.open_current_folder)
        self.open_folder_button.setEnabled(False)
        button_layout.addWidget(self.open_folder_button)
        
        button_layout.addStretch()
        
        # 閉じるボタン
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        parent_layout.addLayout(button_layout)
    
    def start_analysis(self):
        """分析を開始"""
        # 選択されたドライブのパスを取得
        current_drive = self.drive_combo.currentData()
        if current_drive:
            self.current_path = current_drive
        
        # プログレスバーを表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # ボタンを無効化
        self.analyze_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        
        # パスラベルを更新
        self.path_label.setText(f"分析対象: {self.current_path}")
        
        # ワーカースレッドを作成して実行
        self.analysis_worker = DiskAnalysisWorker(self.current_path)
        
        # シグナルを接続
        self.analysis_worker.analysis_completed.connect(self.on_analysis_completed)
        self.analysis_worker.progress_updated.connect(self.on_progress_updated)
        self.analysis_worker.error_occurred.connect(self.on_error_occurred)
        self.analysis_worker.finished.connect(self.on_worker_finished)
        
        # スレッドを開始
        self.analysis_worker.start()
    
    def on_analysis_completed(self, analysis_data):
        """分析完了時の処理"""
        self.current_data = analysis_data
        
        # 小さなアイテムをグループ化
        grouped_data = self.analyzer.group_small_items(analysis_data)
        
        # 円グラフを更新
        self.pie_chart.set_data(grouped_data)
        
        # 詳細リストを更新
        self.update_detail_list(grouped_data)
        
        # ボタンを有効化
        self.open_folder_button.setEnabled(True)
    
    def update_detail_list(self, data_list):
        """詳細リストを更新"""
        self.detail_list.clear()
        
        for item in data_list:
            size_text = self.analyzer.format_size(item['size'])
            percentage = (item['size'] / sum(d['size'] for d in data_list)) * 100 if data_list else 0
            
            item_text = f"{item['name']} - {size_text} ({percentage:.1f}%)"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, item)
            self.detail_list.addItem(list_item)
    
    def on_chart_item_selected(self, item):
        """円グラフのアイテムが選択された時の処理"""
        # 詳細リストで対応するアイテムをハイライト
        for i in range(self.detail_list.count()):
            list_item = self.detail_list.item(i)
            if list_item.data(Qt.UserRole) == item:
                self.detail_list.setCurrentRow(i)
                break
    
    def on_detail_item_double_clicked(self, item):
        """詳細リストのアイテムがダブルクリックされた時の処理"""
        data = item.data(Qt.UserRole)
        if data and data['type'] == 'folder':
            self.current_path = data['path']
            self.start_analysis()
    
    def go_back(self):
        """一つ上のフォルダに戻る"""
        parent_path = os.path.dirname(self.current_path)
        if parent_path and parent_path != self.current_path:
            self.current_path = parent_path
            self.start_analysis()
    
    def open_current_folder(self):
        """現在のフォルダを開く"""
        try:
            if sys.platform == "win32":
                os.startfile(self.current_path)
            elif sys.platform == "darwin":
                os.system(f"open '{self.current_path}'")
            else:
                os.system(f"xdg-open '{self.current_path}'")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"フォルダを開けませんでした: {str(e)}")
    
    def on_progress_updated(self, progress):
        """進捗更新時の処理"""
        self.progress_bar.setValue(progress)
    
    def on_error_occurred(self, error_message):
        """エラー発生時の処理"""
        QMessageBox.warning(self, "エラー", error_message)
    
    def on_worker_finished(self):
        """ワーカースレッド終了時の処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)
        
        # ボタンを有効化
        self.analyze_button.setEnabled(True)
        
        # ワーカースレッドをクリーンアップ
        if self.analysis_worker:
            self.analysis_worker.deleteLater()
            self.analysis_worker = None
    
    def closeEvent(self, event):
        """ダイアログが閉じられる時の処理"""
        # ワーカースレッドが実行中の場合は停止
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.analysis_worker.quit()
            self.analysis_worker.wait(3000)
            if self.analysis_worker.isRunning():
                self.analysis_worker.terminate()
                self.analysis_worker.wait(3000)
        
        super().closeEvent(event)
