#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同一動画ファイル検出機能
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtWidgets import QApplication

# 動画ダイジェスト関連のインポート
try:
    from video_digest import VideoDigestGenerator, OPENCV_AVAILABLE
    VIDEO_DIGEST_AVAILABLE = True
except ImportError:
    VIDEO_DIGEST_AVAILABLE = False
    OPENCV_AVAILABLE = False


class DuplicateVideoDetector(QObject):
    """同一動画ファイル検出クラス"""
    
    # シグナル定義
    duplicates_found = Signal(list)  # 同一サイズの動画ファイルグループのリスト
    progress_updated = Signal(int)  # 進捗（0-100）
    error_occurred = Signal(str)  # エラーメッセージ
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg'}
        self.video_digest_generator = VideoDigestGenerator() if VIDEO_DIGEST_AVAILABLE else None
    
    def is_video_file(self, file_path):
        """動画ファイルかどうかを判定"""
        if not os.path.isfile(file_path):
            return False
        
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.video_extensions
    
    def normalize_filename(self, filename):
        """ファイル名を正規化（比較用）"""
        # 拡張子を除去
        name = Path(filename).stem.lower()
        
        # 特殊文字を除去
        name = re.sub(r'[^\w\s]', '', name)
        
        # 連続する空白を単一の空白に置換
        name = re.sub(r'\s+', ' ', name)
        
        # 前後の空白を除去
        name = name.strip()
        
        return name
    
    def calculate_filename_similarity(self, name1, name2):
        """ファイル名の類似度を計算"""
        norm1 = self.normalize_filename(name1)
        norm2 = self.normalize_filename(name2)
        
        # 完全一致の場合
        if norm1 == norm2:
            return 1.0
        
        # 空の場合
        if not norm1 or not norm2:
            return 0.0
        
        # SequenceMatcherを使用して類似度を計算
        return SequenceMatcher(None, norm1, norm2).ratio()
    
    def find_duplicates_by_size(self, directory_path):
        """指定ディレクトリ内で同一サイズの動画ファイルを検出"""
        if not os.path.isdir(directory_path):
            self.error_occurred.emit(f"ディレクトリが見つかりません: {directory_path}")
            return
        
        try:
            # ディレクトリ内の動画ファイルをスキャン
            video_files = []
            total_files = 0
            
            # まず総ファイル数をカウント
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self.is_video_file(file_path):
                        total_files += 1
            
            if total_files == 0:
                self.duplicates_found.emit([])
                return
            
            # 動画ファイルを収集
            processed_files = 0
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self.is_video_file(file_path):
                        try:
                            file_size = os.path.getsize(file_path)
                            video_files.append({
                                'path': file_path,
                                'size': file_size,
                                'name': file,
                                'directory': root
                            })
                        except OSError:
                            continue  # アクセスできないファイルはスキップ
                        
                        processed_files += 1
                        progress = int((processed_files / total_files) * 100)
                        self.progress_updated.emit(progress)
            
            # サイズでグループ化
            size_groups = defaultdict(list)
            for video_file in video_files:
                size_groups[video_file['size']].append(video_file)
            
            # 複数のファイルがあるサイズグループのみを抽出
            duplicate_groups = []
            for size, files in size_groups.items():
                if len(files) > 1:
                    duplicate_groups.append({
                        'size': size,
                        'files': files,
                        'count': len(files)
                    })
            
            # サイズでソート（大きい順）
            duplicate_groups.sort(key=lambda x: x['size'], reverse=True)
            
            self.progress_updated.emit(100)
            self.duplicates_found.emit(duplicate_groups)
            
        except Exception as e:
            self.error_occurred.emit(f"重複ファイル検出中にエラーが発生しました: {str(e)}")
    
    def find_duplicates_by_name(self, directory_path, similarity_threshold=0.8):
        """指定ディレクトリ内でファイル名が類似している動画ファイルを検出"""
        if not os.path.isdir(directory_path):
            self.error_occurred.emit(f"ディレクトリが見つかりません: {directory_path}")
            return
        
        try:
            # ディレクトリ内の動画ファイルをスキャン
            video_files = []
            total_files = 0
            
            # まず総ファイル数をカウント
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self.is_video_file(file_path):
                        total_files += 1
            
            if total_files == 0:
                self.duplicates_found.emit([])
                return
            
            # 動画ファイルを収集
            processed_files = 0
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self.is_video_file(file_path):
                        try:
                            file_size = os.path.getsize(file_path)
                            video_files.append({
                                'path': file_path,
                                'size': file_size,
                                'name': file,
                                'directory': root
                            })
                        except OSError:
                            continue  # アクセスできないファイルはスキップ
                        
                        processed_files += 1
                        progress = int((processed_files / total_files) * 50)  # 前半50%でファイル収集
                        self.progress_updated.emit(progress)
            
            # ファイル名の類似性でグループ化
            similar_groups = []
            processed_files = set()
            
            for i, file1 in enumerate(video_files):
                if file1['path'] in processed_files:
                    continue
                
                similar_files = [file1]
                processed_files.add(file1['path'])
                
                for j, file2 in enumerate(video_files[i+1:], i+1):
                    if file2['path'] in processed_files:
                        continue
                    
                    similarity = self.calculate_filename_similarity(file1['name'], file2['name'])
                    if similarity >= similarity_threshold:
                        similar_files.append(file2)
                        processed_files.add(file2['path'])
                
                if len(similar_files) > 1:
                    # 類似度の平均を計算
                    similarities = []
                    for file_a in similar_files:
                        for file_b in similar_files:
                            if file_a['path'] != file_b['path']:
                                sim = self.calculate_filename_similarity(file_a['name'], file_b['name'])
                                similarities.append(sim)
                    
                    avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
                    
                    similar_groups.append({
                        'type': 'name',
                        'files': similar_files,
                        'count': len(similar_files),
                        'similarity': avg_similarity,
                        'size': sum(f['size'] for f in similar_files)
                    })
                
                # 進捗更新（後半50%で類似性計算）
                progress = 50 + int((i / len(video_files)) * 50)
                self.progress_updated.emit(progress)
            
            # 類似度でソート（高い順）
            similar_groups.sort(key=lambda x: x['similarity'], reverse=True)
            
            self.progress_updated.emit(100)
            self.duplicates_found.emit(similar_groups)
            
        except Exception as e:
            self.error_occurred.emit(f"類似ファイル名検出中にエラーが発生しました: {str(e)}")
    
    def compare_video_digests(self, video_paths, max_thumbnails=6, similarity_threshold=0.8):
        """動画のダイジェストを比較して同一性を判定"""
        if not VIDEO_DIGEST_AVAILABLE or not self.video_digest_generator:
            return None
        
        try:
            # 各動画のダイジェストを生成
            digests = {}
            for video_path in video_paths:
                if os.path.exists(video_path):
                    # ダイジェスト生成（同期処理）
                    thumbnails = self._generate_digest_sync(video_path, max_thumbnails)
                    if thumbnails:
                        digests[video_path] = thumbnails
            
            if len(digests) < 2:
                return None
            
            # ダイジェストを比較
            similar_groups = []
            processed_paths = set()
            
            for path1, digest1 in digests.items():
                if path1 in processed_paths:
                    continue
                
                similar_files = [path1]
                processed_paths.add(path1)
                
                for path2, digest2 in digests.items():
                    if path2 in processed_paths:
                        continue
                    
                    similarity = self._calculate_similarity(digest1, digest2)
                    if similarity >= similarity_threshold:
                        similar_files.append(path2)
                        processed_paths.add(path2)
                
                if len(similar_files) > 1:
                    similar_groups.append({
                        'files': similar_files,
                        'similarity': similarity
                    })
            
            return similar_groups
            
        except Exception as e:
            return None
    
    def _generate_digest_sync(self, video_path, max_thumbnails=6):
        """同期でダイジェストを生成"""
        if not VIDEO_DIGEST_AVAILABLE or not self.video_digest_generator:
            return None
        
        try:
            # 動画ファイルを開く
            import cv2
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # 動画の情報を取得
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                cap.release()
                return None
            
            # サムネイルを生成するフレーム位置を計算
            frame_positions = []
            if max_thumbnails == 1:
                frame_positions = [total_frames // 2]
            else:
                step = total_frames // (max_thumbnails + 1)
                frame_positions = [step * (i + 1) for i in range(max_thumbnails)]
            
            thumbnails = []
            for frame_pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                
                if ret:
                    # フレームをリサイズ（比較用に小さく）
                    resized_frame = cv2.resize(frame, (80, 45))
                    # OpenCVのBGRからRGBに変換
                    rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                    thumbnails.append(rgb_frame)
                else:
                    # フレームの読み込みに失敗した場合は空の配列を追加
                    thumbnails.append(None)
            
            cap.release()
            return thumbnails
            
        except Exception as e:
            return None
    
    def _calculate_similarity(self, digest1, digest2):
        """2つのダイジェストの類似度を計算"""
        if not digest1 or not digest2:
            return 0.0
        
        if len(digest1) != len(digest2):
            return 0.0
        
        try:
            import cv2
            import numpy as np
            
            total_similarity = 0.0
            valid_comparisons = 0
            
            for i, (frame1, frame2) in enumerate(zip(digest1, digest2)):
                if frame1 is None or frame2 is None:
                    continue
                
                # ヒストグラム比較
                hist1 = cv2.calcHist([frame1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                hist2 = cv2.calcHist([frame2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                
                # ヒストグラムの相関を計算
                correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
                total_similarity += correlation
                valid_comparisons += 1
            
            if valid_comparisons == 0:
                return 0.0
            
            return total_similarity / valid_comparisons
            
        except Exception as e:
            return 0.0


class DuplicateVideoWorker(QThread):
    """同一動画検出用のワーカースレッド"""
    
    def __init__(self, directory_path, detection_type="size", similarity_threshold=0.8, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.detection_type = detection_type
        self.similarity_threshold = similarity_threshold
        self.detector = DuplicateVideoDetector()
        
        # シグナルを接続
        self.detector.duplicates_found.connect(self.duplicates_found)
        self.detector.progress_updated.connect(self.progress_updated)
        self.detector.error_occurred.connect(self.error_occurred)
    
    def run(self):
        """スレッドの実行"""
        if self.detection_type == "size":
            self.detector.find_duplicates_by_size(self.directory_path)
        elif self.detection_type == "name":
            self.detector.find_duplicates_by_name(self.directory_path, self.similarity_threshold)
    
    # シグナルを転送
    duplicates_found = Signal(list)
    progress_updated = Signal(int)
    error_occurred = Signal(str)
