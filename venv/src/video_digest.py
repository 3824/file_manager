#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画ファイルのダイジェスト生成機能
"""

import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QApplication

# OpenCVとNumPyのインポート（オプショナル）
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None


class VideoDigestGenerator(QObject):
    """動画ダイジェスト生成クラス"""
    
    # シグナル定義
    digest_generated = Signal(str, list)  # ファイルパス, サムネイル画像のリスト
    progress_updated = Signal(int)  # 進捗（0-100）
    error_occurred = Signal(str)  # エラーメッセージ
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg'}
        self.max_thumbnails = 6  # デフォルトのサムネイル数
        self.thumbnail_size = (160, 90)  # デフォルトのサムネイルサイズ
        
    def is_video_file(self, file_path):
        """動画ファイルかどうかを判定"""
        if not os.path.isfile(file_path):
            return False
        
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.video_extensions
    
    def generate_digest(self, video_path, max_thumbnails=None, thumbnail_size=None):
        """動画のダイジェストを生成"""
        if not OPENCV_AVAILABLE:
            self.error_occurred.emit("OpenCVがインストールされていません。動画ダイジェスト機能を使用するには、'pip install opencv-python'を実行してください。")
            return
        
        if not self.is_video_file(video_path):
            self.error_occurred.emit(f"動画ファイルではありません: {video_path}")
            return
        
        if not os.path.exists(video_path):
            self.error_occurred.emit(f"ファイルが見つかりません: {video_path}")
            return
        
        # パラメータの設定
        if max_thumbnails is None:
            max_thumbnails = self.max_thumbnails
        if thumbnail_size is None:
            thumbnail_size = self.thumbnail_size
        
        try:
            # 動画ファイルを開く
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.error_occurred.emit(f"動画ファイルを開けませんでした: {video_path}")
                return
            
            # 動画の情報を取得
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            if total_frames == 0:
                self.error_occurred.emit("動画にフレームが含まれていません")
                cap.release()
                return
            
            # サムネイルを生成するフレーム位置を計算
            frame_positions = []
            if max_thumbnails == 1:
                # 1つの場合は中央のフレーム
                frame_positions = [total_frames // 2]
            else:
                # 複数の場合は等間隔で配置
                step = total_frames // (max_thumbnails + 1)
                frame_positions = [step * (i + 1) for i in range(max_thumbnails)]
            
            thumbnails = []
            for i, frame_pos in enumerate(frame_positions):
                # 進捗を更新
                progress = int((i / len(frame_positions)) * 100)
                self.progress_updated.emit(progress)
                
                # 指定されたフレームに移動
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                
                if ret:
                    # フレームをリサイズ
                    resized_frame = cv2.resize(frame, thumbnail_size)
                    
                    # OpenCVのBGRからRGBに変換
                    rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                    
                    # QImageに変換
                    h, w, ch = rgb_frame.shape
                    bytes_per_line = ch * w
                    qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    
                    # QPixmapに変換
                    pixmap = QPixmap.fromImage(qt_image)
                    thumbnails.append(pixmap)
                else:
                    # フレームの読み込みに失敗した場合は空のQPixmapを追加
                    empty_pixmap = QPixmap(thumbnail_size[0], thumbnail_size[1])
                    empty_pixmap.fill()
                    thumbnails.append(empty_pixmap)
            
            cap.release()
            
            # 進捗を100%に設定
            self.progress_updated.emit(100)
            
            # ダイジェスト生成完了を通知
            self.digest_generated.emit(video_path, thumbnails)
            
        except Exception as e:
            self.error_occurred.emit(f"ダイジェスト生成中にエラーが発生しました: {str(e)}")
    
    def get_video_info(self, video_path):
        """動画の基本情報を取得"""
        if not OPENCV_AVAILABLE:
            return None
        
        if not self.is_video_file(video_path):
            return None
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # 動画の情報を取得
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            duration = total_frames / fps if fps > 0 else 0
            
            cap.release()
            
            return {
                'duration': duration,
                'fps': fps,
                'width': width,
                'height': height,
                'total_frames': total_frames,
                'file_size': os.path.getsize(video_path)
            }
        except Exception as e:
            return None


class VideoDigestWorker(QThread):
    """動画ダイジェスト生成用のワーカースレッド"""
    
    def __init__(self, video_path, max_thumbnails=6, thumbnail_size=(160, 90), parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.max_thumbnails = max_thumbnails
        self.thumbnail_size = thumbnail_size
        self.generator = VideoDigestGenerator()
        
        # シグナルを接続
        self.generator.digest_generated.connect(self.digest_generated)
        self.generator.progress_updated.connect(self.progress_updated)
        self.generator.error_occurred.connect(self.error_occurred)
    
    def run(self):
        """スレッドの実行"""
        self.generator.generate_digest(
            self.video_path, 
            self.max_thumbnails, 
            self.thumbnail_size
        )
    
    # シグナルを転送
    digest_generated = Signal(str, list)
    progress_updated = Signal(int)
    error_occurred = Signal(str)
