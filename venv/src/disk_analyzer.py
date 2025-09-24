#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ディスク使用量分析機能
"""

import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtWidgets import QApplication


class DiskAnalyzer(QObject):
    """ディスク使用量分析クラス"""
    
    # シグナル定義
    analysis_completed = Signal(list)  # 分析完了（フォルダ情報のリスト）
    progress_updated = Signal(int)  # 進捗（0-100）
    error_occurred = Signal(str)  # エラーメッセージ
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_depth = 3  # 最大分析深度
        self.min_size_threshold = 1024 * 1024  # 1MB以下のフォルダは「その他」にまとめる
    
    def analyze_directory(self, directory_path):
        """指定ディレクトリの使用量を分析"""
        if not os.path.isdir(directory_path):
            self.error_occurred.emit(f"ディレクトリが見つかりません: {directory_path}")
            return
        
        try:
            # ディレクトリ内のフォルダとファイルを分析
            folder_info = self._analyze_folder_recursive(directory_path, 0)
            
            # 結果をソート（サイズの大きい順）
            folder_info.sort(key=lambda x: x['size'], reverse=True)
            
            self.analysis_completed.emit(folder_info)
            
        except Exception as e:
            self.error_occurred.emit(f"分析中にエラーが発生しました: {str(e)}")
    
    def _analyze_folder_recursive(self, folder_path, current_depth):
        """フォルダを再帰的に分析"""
        if current_depth > self.max_depth:
            return []
        
        try:
            folder_info_list = []
            
            # フォルダ内のアイテムを取得
            items = []
            try:
                for item in os.listdir(folder_path):
                    item_path = os.path.join(folder_path, item)
                    if os.path.exists(item_path):
                        items.append(item_path)
            except PermissionError:
                # アクセス権限がない場合はスキップ
                return []
            
            # 各アイテムのサイズを計算
            for item_path in items:
                try:
                    if os.path.isdir(item_path):
                        # フォルダの場合
                        folder_size = self._calculate_folder_size(item_path)
                        folder_name = os.path.basename(item_path)
                        
                        folder_info = {
                            'name': folder_name,
                            'path': item_path,
                            'size': folder_size,
                            'type': 'folder',
                            'depth': current_depth + 1,
                            'children': self._analyze_folder_recursive(item_path, current_depth + 1) if current_depth < self.max_depth else []
                        }
                        folder_info_list.append(folder_info)
                    
                    elif os.path.isfile(item_path):
                        # ファイルの場合
                        file_size = os.path.getsize(item_path)
                        file_name = os.path.basename(item_path)
                        
                        file_info = {
                            'name': file_name,
                            'path': item_path,
                            'size': file_size,
                            'type': 'file',
                            'depth': current_depth + 1,
                            'children': []
                        }
                        folder_info_list.append(file_info)
                
                except (OSError, PermissionError):
                    # アクセスできないファイル/フォルダはスキップ
                    continue
            
            return folder_info_list
            
        except Exception as e:
            print(f"フォルダ分析エラー ({folder_path}): {e}")
            return []
    
    def _calculate_folder_size(self, folder_path):
        """フォルダのサイズを計算"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    try:
                        file_path = os.path.join(dirpath, filename)
                        if os.path.exists(file_path):
                            total_size += os.path.getsize(file_path)
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        
        return total_size
    
    def get_drive_info(self, drive_path):
        """ドライブ情報を取得"""
        try:
            if sys.platform == "win32":
                import shutil
                total, used, free = shutil.disk_usage(drive_path)
                return {
                    'total': total,
                    'used': used,
                    'free': free,
                    'path': drive_path
                }
            else:
                import shutil
                total, used, free = shutil.disk_usage(drive_path)
                return {
                    'total': total,
                    'used': used,
                    'free': free,
                    'path': drive_path
                }
        except Exception as e:
            return None
    
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
    
    def group_small_items(self, items, threshold=None):
        """小さなアイテムを「その他」としてグループ化"""
        if threshold is None:
            threshold = self.min_size_threshold
        
        large_items = []
        small_items = []
        small_total_size = 0
        
        for item in items:
            if item['size'] >= threshold:
                large_items.append(item)
            else:
                small_items.append(item)
                small_total_size += item['size']
        
        # 「その他」グループを作成
        if small_items:
            other_group = {
                'name': f"その他 ({len(small_items)}個)",
                'path': '',
                'size': small_total_size,
                'type': 'group',
                'depth': 0,
                'children': small_items
            }
            large_items.append(other_group)
        
        return large_items


class DiskAnalysisWorker(QThread):
    """ディスク分析用のワーカースレッド"""
    
    def __init__(self, directory_path, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.analyzer = DiskAnalyzer()
        
        # シグナルを接続
        self.analyzer.analysis_completed.connect(self.analysis_completed)
        self.analyzer.progress_updated.connect(self.progress_updated)
        self.analyzer.error_occurred.connect(self.error_occurred)
    
    def run(self):
        """スレッドの実行"""
        self.analyzer.analyze_directory(self.directory_path)
    
    # シグナルを転送
    analysis_completed = Signal(list)
    progress_updated = Signal(int)
    error_occurred = Signal(str)
