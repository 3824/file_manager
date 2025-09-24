#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル検索機能
"""

import os
import sys
import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtWidgets import QApplication


class FileSearchIndex(QObject):
    """ファイル検索インデックス管理クラス"""
    
    # シグナル定義
    index_updated = Signal(int)  # インデックス更新完了（インデックスされたファイル数）
    progress_updated = Signal(int)  # 進捗（0-100）
    error_occurred = Signal(str)  # エラーメッセージ
    
    def __init__(self, index_db_path=None, parent=None):
        super().__init__(parent)
        if index_db_path is None:
            index_db_path = os.path.join(os.path.expanduser("~"), ".file_manager_index.db")
        
        self.index_db_path = index_db_path
        self.init_database()
    
    def init_database(self):
        """データベースを初期化"""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            # ファイル情報テーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    is_directory INTEGER NOT NULL,
                    extension TEXT,
                    indexed_time REAL NOT NULL
                )
            ''')
            
            # 検索用インデックス
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_name ON files(name)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_path ON files(path)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_extension ON files(extension)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_modified ON files(modified_time)
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.error_occurred.emit(f"データベース初期化エラー: {str(e)}")
    
    def add_file_to_index(self, file_path, file_info):
        """ファイルをインデックスに追加"""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO files 
                (path, name, size, modified_time, is_directory, extension, indexed_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                file_info['name'],
                file_info['size'],
                file_info['modified_time'],
                file_info['is_directory'],
                file_info['extension'],
                time.time()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"ファイルインデックス追加エラー: {e}")
    
    def remove_file_from_index(self, file_path):
        """ファイルをインデックスから削除"""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM files WHERE path = ?', (file_path,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"ファイルインデックス削除エラー: {e}")
    
    def search_files(self, query, search_type="name", limit=100):
        """ファイルを検索"""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            if search_type == "name":
                # ファイル名で検索（部分一致）
                cursor.execute('''
                    SELECT path, name, size, modified_time, is_directory, extension
                    FROM files 
                    WHERE name LIKE ? 
                    ORDER BY modified_time DESC 
                    LIMIT ?
                ''', (f"%{query}%", limit))
            
            elif search_type == "extension":
                # 拡張子で検索
                cursor.execute('''
                    SELECT path, name, size, modified_time, is_directory, extension
                    FROM files 
                    WHERE extension = ? 
                    ORDER BY modified_time DESC 
                    LIMIT ?
                ''', (query.lower(), limit))
            
            elif search_type == "path":
                # パスで検索（部分一致）
                cursor.execute('''
                    SELECT path, name, size, modified_time, is_directory, extension
                    FROM files 
                    WHERE path LIKE ? 
                    ORDER BY modified_time DESC 
                    LIMIT ?
                ''', (f"%{query}%", limit))
            
            elif search_type == "size_range":
                # サイズ範囲で検索
                try:
                    size_parts = query.split('-')
                    if len(size_parts) == 2:
                        min_size = int(size_parts[0].strip())
                        max_size = int(size_parts[1].strip())
                        cursor.execute('''
                            SELECT path, name, size, modified_time, is_directory, extension
                            FROM files 
                            WHERE size >= ? AND size <= ? 
                            ORDER BY size DESC 
                            LIMIT ?
                        ''', (min_size, max_size, limit))
                except ValueError:
                    return []
            
            results = cursor.fetchall()
            conn.close()
            
            # 結果を辞書形式に変換
            file_list = []
            for row in results:
                file_list.append({
                    'path': row[0],
                    'name': row[1],
                    'size': row[2],
                    'modified_time': row[3],
                    'is_directory': bool(row[4]),
                    'extension': row[5]
                })
            
            return file_list
            
        except Exception as e:
            self.error_occurred.emit(f"検索エラー: {str(e)}")
            return []
    
    def get_file_info(self, file_path):
        """ファイル情報を取得"""
        try:
            if not os.path.exists(file_path):
                return None
            
            stat = os.stat(file_path)
            is_directory = os.path.isdir(file_path)
            path_obj = Path(file_path)
            
            return {
                'name': path_obj.name,
                'size': stat.st_size,
                'modified_time': stat.st_mtime,
                'is_directory': is_directory,
                'extension': path_obj.suffix.lower() if not is_directory else None
            }
            
        except Exception as e:
            return None
    
    def update_index_for_directory(self, directory_path):
        """指定ディレクトリのインデックスを更新"""
        if not os.path.isdir(directory_path):
            self.error_occurred.emit(f"ディレクトリが見つかりません: {directory_path}")
            return
        
        try:
            # ディレクトリ内のファイルをスキャン
            all_files = []
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    all_files.append(file_path)
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    all_files.append(dir_path)
            
            if not all_files:
                self.index_updated.emit(0)
                return
            
            # ファイルをインデックスに追加
            indexed_count = 0
            for i, file_path in enumerate(all_files):
                file_info = self.get_file_info(file_path)
                if file_info:
                    self.add_file_to_index(file_path, file_info)
                    indexed_count += 1
                
                # 進捗更新
                progress = int((i / len(all_files)) * 100)
                self.progress_updated.emit(progress)
            
            self.progress_updated.emit(100)
            self.index_updated.emit(indexed_count)
            
        except Exception as e:
            self.error_occurred.emit(f"インデックス更新エラー: {str(e)}")
    
    def get_index_stats(self):
        """インデックス統計情報を取得"""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            # 総ファイル数
            cursor.execute('SELECT COUNT(*) FROM files')
            total_files = cursor.fetchone()[0]
            
            # 総ディレクトリ数
            cursor.execute('SELECT COUNT(*) FROM files WHERE is_directory = 1')
            total_dirs = cursor.fetchone()[0]
            
            # 最新のインデックス更新時刻
            cursor.execute('SELECT MAX(indexed_time) FROM files')
            last_update = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_files': total_files,
                'total_directories': total_dirs,
                'last_update': last_update
            }
            
        except Exception as e:
            return None


class FileSearchWorker(QThread):
    """ファイル検索用のワーカースレッド"""
    
    def __init__(self, query, search_type="name", limit=100, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_type = search_type
        self.limit = limit
        self.search_index = FileSearchIndex()
        
        # シグナルを接続
        self.search_index.error_occurred.connect(self.error_occurred)
    
    def run(self):
        """スレッドの実行"""
        results = self.search_index.search_files(self.query, self.search_type, self.limit)
        self.search_completed.emit(results)
    
    # シグナル定義
    search_completed = Signal(list)
    error_occurred = Signal(str)


class IndexUpdateWorker(QThread):
    """インデックス更新用のワーカースレッド"""
    
    def __init__(self, directory_path, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.search_index = FileSearchIndex()
        
        # シグナルを接続
        self.search_index.index_updated.connect(self.index_updated)
        self.search_index.progress_updated.connect(self.progress_updated)
        self.search_index.error_occurred.connect(self.error_occurred)
    
    def run(self):
        """スレッドの実行"""
        self.search_index.update_index_for_directory(self.directory_path)
    
    # シグナルを転送
    index_updated = Signal(int)
    progress_updated = Signal(int)
    error_occurred = Signal(str)
