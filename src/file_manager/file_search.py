#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File search indexing utilities."""

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
    """Manage the SQLite index used by the search feature."""
    
    # 繧ｷ繧ｰ繝翫Ν螳夂ｾｩ
    index_updated = Signal(int)  # 繧､繝ｳ繝・ャ繧ｯ繧ｹ譖ｴ譁ｰ螳御ｺ・ｼ医う繝ｳ繝・ャ繧ｯ繧ｹ縺輔ｌ縺溘ヵ繧｡繧､繝ｫ謨ｰ・・
    progress_updated = Signal(int)  # 騾ｲ謐暦ｼ・-100・・
    error_occurred = Signal(str)  # 繧ｨ繝ｩ繝ｼ繝｡繝・そ繝ｼ繧ｸ
    
    def __init__(self, index_db_path=None, parent=None):
        super().__init__(parent)
        if index_db_path is None:
            index_db_path = os.path.join(os.path.expanduser("~"), ".file_manager_index.db")
        
        self.index_db_path = index_db_path
        self.init_database()
    
    def init_database(self):
        """Ensure the index database and schema exist."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            # 繝輔ぃ繧､繝ｫ諠・ｱ繝・・繝悶Ν
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    is_directory INTEGER NOT NULL,
                    extension TEXT,
                    indexed_time REAL NOT NULL,
                    directory TEXT,
                    content_hash TEXT
                )
            ''')
            
            # 讀懃ｴ｢逕ｨ繧､繝ｳ繝・ャ繧ｯ繧ｹ
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
            cursor.execute("PRAGMA table_info(files)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            if 'directory' not in existing_columns:
                cursor.execute("ALTER TABLE files ADD COLUMN directory TEXT")
            if 'content_hash' not in existing_columns:
                cursor.execute("ALTER TABLE files ADD COLUMN content_hash TEXT")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.error_occurred.emit(f"繝・・繧ｿ繝吶・繧ｹ蛻晄悄蛹悶お繝ｩ繝ｼ: {str(e)}")
    
    def add_file_to_index(self, file_path, file_info):
        """Insert or update a single entry in the index."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO files 
                (path, name, size, modified_time, is_directory, extension, indexed_time, directory, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                file_info['name'],
                file_info['size'],
                file_info['modified_time'],
                file_info['is_directory'],
                file_info['extension'],
                time.time(),
                file_info['directory'],
                file_info.get('content_hash')
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"繝輔ぃ繧､繝ｫ繧､繝ｳ繝・ャ繧ｯ繧ｹ霑ｽ蜉繧ｨ繝ｩ繝ｼ: {e}")
    
    def remove_file_from_index(self, file_path):
        """Delete an entry from the index database."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM files WHERE path = ?', (file_path,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"繝輔ぃ繧､繝ｫ繧､繝ｳ繝・ャ繧ｯ繧ｹ蜑企勁繧ｨ繝ｩ繝ｼ: {e}")
    
    def search_files(self, query, search_type="name", limit=100, scope_path=None):
        """Run a search query against the SQLite index."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()

            safe_limit = max(1, int(limit))
            where_parts = []
            params = []
            order_by = "modified_time DESC"

            normalized_scope = None
            if scope_path:
                normalized_scope = self._normalize_path(scope_path)
                if not os.path.isdir(normalized_scope):
                    conn.close()
                    return []
                scope_prefix = normalized_scope
                if not scope_prefix.endswith(os.sep):
                    scope_prefix = scope_prefix + os.sep
                where_parts.append('(LOWER(path) = LOWER(?) OR LOWER(path) LIKE LOWER(?))')
                params.extend([normalized_scope, f"{scope_prefix}%"])

            normalized_query = (query or '').strip()

            if search_type == "name":
                where_parts.append('LOWER(name) LIKE LOWER(?)')
                params.append(f"%{normalized_query}%")
            elif search_type == "extension":
                normalized_ext = normalized_query.lower()
                if normalized_ext and not normalized_ext.startswith('.'):
                    normalized_ext = f'.{normalized_ext}'
                where_parts.append('LOWER(extension) = ?')
                params.append(normalized_ext)
            elif search_type == "path":
                where_parts.append('LOWER(path) LIKE LOWER(?)')
                params.append(f"%{normalized_query}%")
            elif search_type == "size_range":
                size_parts = [part.strip() for part in normalized_query.split('-', 1)]
                if len(size_parts) != 2 or not size_parts[0] or not size_parts[1]:
                    conn.close()
                    return []
                try:
                    min_size = int(size_parts[0])
                    max_size = int(size_parts[1])
                except ValueError:
                    conn.close()
                    return []
                if min_size > max_size:
                    min_size, max_size = max_size, min_size
                where_parts.append('size >= ?')
                where_parts.append('size <= ?')
                params.extend([min_size, max_size])
                order_by = "size DESC"
            else:
                where_parts.append('LOWER(name) LIKE LOWER(?)')
                params.append(f"%{normalized_query}%")

            query_sql = (
                "SELECT path, name, size, modified_time, is_directory, extension FROM files "
            )
            if where_parts:
                query_sql += "WHERE " + " AND ".join(where_parts) + " "
            query_sql += f"ORDER BY {order_by} LIMIT ?"
            params.append(safe_limit)

            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            conn.close()

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
            self.error_occurred.emit(f"讀懃ｴ｢繧ｨ繝ｩ繝ｼ: {str(e)}")
            return []
    @staticmethod
    def _normalize_path(path):
        normalized = os.path.abspath(path)
        normalized = os.path.normpath(normalized)
        if os.name == "nt":
            normalized = os.path.normcase(normalized)
        return normalized

    def get_file_info(self, file_path):
        """Collect file metadata used for indexing."""
        try:
            if not os.path.exists(file_path):
                return None
            
            stat = os.stat(file_path)
            is_directory = os.path.isdir(file_path)
            path_obj = Path(file_path)
            
            directory = self._normalize_path(str(path_obj.parent))
            return {
                'name': path_obj.name,
                'size': stat.st_size,
                'modified_time': stat.st_mtime,
                'is_directory': is_directory,
                'extension': path_obj.suffix.lower() if not is_directory else None,
                'directory': directory,
                'content_hash': None
            }
            
        except Exception as e:
            return None
    
    def update_index_for_directory(self, directory_path):
        """Traverse a directory and refresh index records."""
        if not os.path.isdir(directory_path):
            self.error_occurred.emit(f"繝・ぅ繝ｬ繧ｯ繝医Μ縺瑚ｦ九▽縺九ｊ縺ｾ縺帙ｓ: {directory_path}")
            return
        
        try:
            # 繝・ぅ繝ｬ繧ｯ繝医Μ蜀・・繝輔ぃ繧､繝ｫ繧偵せ繧ｭ繝｣繝ｳ
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
            
            # 繝輔ぃ繧､繝ｫ繧偵う繝ｳ繝・ャ繧ｯ繧ｹ縺ｫ霑ｽ蜉
            indexed_count = 0
            for i, file_path in enumerate(all_files):
                file_info = self.get_file_info(file_path)
                if file_info:
                    self.add_file_to_index(file_path, file_info)
                    indexed_count += 1
                
                # 騾ｲ謐玲峩譁ｰ
                progress = int((i / len(all_files)) * 100)
                self.progress_updated.emit(progress)
            
            self.progress_updated.emit(100)
            self.index_updated.emit(indexed_count)
            
        except Exception as e:
            self.error_occurred.emit(f"繧､繝ｳ繝・ャ繧ｯ繧ｹ譖ｴ譁ｰ繧ｨ繝ｩ繝ｼ: {str(e)}")
    
    def get_index_stats(self):
        """Return summary statistics about the index contents."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            
            # 邱上ヵ繧｡繧､繝ｫ謨ｰ
            cursor.execute('SELECT COUNT(*) FROM files')
            total_files = cursor.fetchone()[0]
            
            # 邱上ョ繧｣繝ｬ繧ｯ繝医Μ謨ｰ
            cursor.execute('SELECT COUNT(*) FROM files WHERE is_directory = 1')
            total_dirs = cursor.fetchone()[0]
            
            # 譛譁ｰ縺ｮ繧､繝ｳ繝・ャ繧ｯ繧ｹ譖ｴ譁ｰ譎ょ綾
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
    """Execute search queries in a background thread."""

    def __init__(self, query, search_type="name", limit=100, *, scope_path=None, index_db_path=None, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_type = search_type
        self.limit = limit
        self.scope_path = os.fspath(scope_path) if scope_path else None
        self.index_db_path = index_db_path
        self.search_index = FileSearchIndex(index_db_path=index_db_path)

        # 繧ｷ繧ｰ繝翫Ν繧呈磁邯・
        self.search_index.error_occurred.connect(self.error_occurred)

    def run(self):
        """Execute the file search in the worker thread."""
        try:
            results = self.search_index.search_files(
                self.query,
                self.search_type,
                self.limit,
                scope_path=self.scope_path,
            )
            self.search_completed.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))

    # 繧ｷ繧ｰ繝翫Ν螳夂ｾｩ
    search_completed = Signal(list)
    error_occurred = Signal(str)


class IndexUpdateWorker(QThread):
    """Update index data for a directory on a worker thread."""

    def __init__(self, directory_path, index_db_path=None, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.index_db_path = index_db_path
        self.search_index = FileSearchIndex(index_db_path=index_db_path)

        # 繧ｷ繧ｰ繝翫Ν繧呈磁邯・
        self.search_index.index_updated.connect(self.index_updated)
        self.search_index.progress_updated.connect(self.progress_updated)
        self.search_index.error_occurred.connect(self.error_occurred)

    def run(self):
        """Execute the directory index refresh."""
        self.search_index.update_index_for_directory(self.directory_path)

    # 繧ｷ繧ｰ繝翫Ν繧定ｻ｢騾・
    index_updated = Signal(int)
    progress_updated = Signal(int)
    error_occurred = Signal(str)


