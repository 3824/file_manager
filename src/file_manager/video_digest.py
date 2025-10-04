#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画ファイルのダイジェスト生成機能
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from .video_features import VideoFeatures, extract_video_features

# OpenCVとNumPyのインポート
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
    
    def generate_digest(self, video_path, max_thumbnails=None, thumbnail_size=None) -> Optional[VideoFeatures]:
        """動画のダイジェストを生成

        OpenCVが利用できない場合は、実行時エラーではなくプレースホルダーのサムネイルを
        生成して `digest_generated` を発行するフォールバックを提供します。
        これにより、UIはサムネイルがなくても正常に動作します。

        Returns:
            Optional[VideoFeatures]: 動画の特徴量情報。OpenCVが利用できない場合はNone。
        """
        # フォールバック: OpenCVがない場合はプレースホルダー画像を返す
        if not OPENCV_AVAILABLE:
            # パラメータの決定
            if max_thumbnails is None:
                max_thumbnails = self.max_thumbnails
            if thumbnail_size is None:
                thumbnail_size = self.thumbnail_size

            try:
                thumbnails = []
                for i in range(max_thumbnails):
                    pixmap = QPixmap(thumbnail_size[0], thumbnail_size[1])
                    pixmap.fill()  # 空の（透明/白）pixmap
                    thumbnails.append(pixmap)

                # 進捗を段階的に更新
                for p in range(0, 101, max(1, 100 // max(1, max_thumbnails))):
                    self.progress_updated.emit(min(p, 100))

                # 最後にdigest_generatedを発行
                self.digest_generated.emit(video_path, thumbnails)
                return None
            except Exception as e:
                self.error_occurred.emit(f"プレースホルダーサムネイル生成に失敗しました: {e}")
                return None
        
        if not self.is_video_file(video_path):
            self.error_occurred.emit(f"動画ファイルではありません: {video_path}")
            return None
        
        if not os.path.exists(video_path):
            self.error_occurred.emit(f"ファイルが見つかりません: {video_path}")
            return None
        
        # パラメータの設定
        if max_thumbnails is None:
            max_thumbnails = self.max_thumbnails
        if thumbnail_size is None:
            thumbnail_size = self.thumbnail_size
            
        # 特徴量抽出
        try:
            features = extract_video_features(
                video_path,
                max_thumbnails=max_thumbnails,
                progress_callback=lambda p: self.progress_updated.emit(p)
            )
            if not features:
                self.error_occurred.emit(f"動画の特徴量抽出に失敗しました: {video_path}")
                return None
                
            # サムネイル画像の生成
            thumbnails = []
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.error_occurred.emit(f"動画ファイルを開けませんでした: {video_path}")
                return None
                
            try:
                for pos in features.thumbnail_positions:
                    frame_pos = int(pos * features.frame_count)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                    ret, frame = cap.read()
                    if not ret:
                        continue
                        
                    # フレームをリサイズ
                    aspect_ratio = frame.shape[1] / frame.shape[0]
                    w = thumbnail_size[0]
                    h = int(w / aspect_ratio)
                    if h > thumbnail_size[1]:
                        h = thumbnail_size[1]
                        w = int(h * aspect_ratio)
                    frame = cv2.resize(frame, (w, h))
                    
                    # BGR -> RGB変換
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # QPixmapに変換
                    qimg = QImage(frame.data, frame.shape[1], frame.shape[0],
                                frame.strides[0], QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg)
                    
                    # 中央寄せでリサイズ
                    if w != thumbnail_size[0] or h != thumbnail_size[1]:
                        bg = QPixmap(thumbnail_size[0], thumbnail_size[1])
                        bg.fill()
                        x = (thumbnail_size[0] - w) // 2
                        y = (thumbnail_size[1] - h) // 2
                        painter = QPainter(bg)
                        painter.drawPixmap(x, y, pixmap)
                        painter.end()
                        pixmap = bg
                        
                    thumbnails.append(pixmap)
                    
            finally:
                cap.release()
                
            # サムネイル生成が完了したらシグナルを発行
            self.digest_generated.emit(video_path, thumbnails)
            return features
                    
        except Exception as e:
            self.error_occurred.emit(f"サムネイル生成に失敗しました: {e}")
            return None
            
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
