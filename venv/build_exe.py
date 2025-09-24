#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller用のビルドスクリプト
"""

import os
import sys
import subprocess
from pathlib import Path

def build_executable():
    """実行ファイルをビルド"""
    
    # PyInstallerのコマンドを構築
    cmd = [
        "pyinstaller",
        "--onefile",  # 単一ファイルとしてビルド
        "--windowed",  # コンソールウィンドウを非表示
        "--name=GUIファイラー",
        "--icon=assets/icons/app_icon.ico",  # アイコンファイル（存在する場合）
        "--add-data=assets;assets",  # アセットファイルを含める
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui", 
        "--hidden-import=PySide6.QtWidgets",
        "run.py"
    ]
    
    # アイコンファイルが存在しない場合はアイコンオプションを削除
    if not os.path.exists("assets/icons/app_icon.ico"):
        cmd = [arg for arg in cmd if not arg.startswith("--icon")]
    
    # アセットディレクトリが存在しない場合はアセットオプションを削除
    if not os.path.exists("assets"):
        cmd = [arg for arg in cmd if not arg.startswith("--add-data")]
    
    print("ビルドコマンド:", " ".join(cmd))
    
    try:
        # PyInstallerを実行
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("ビルドが完了しました！")
        print("実行ファイルは dist/ ディレクトリに作成されました。")
        
    except subprocess.CalledProcessError as e:
        print(f"ビルドエラー: {e}")
        print(f"エラー出力: {e.stderr}")
        return False
    
    except FileNotFoundError:
        print("PyInstallerが見つかりません。以下のコマンドでインストールしてください:")
        print("pip install pyinstaller")
        return False
    
    return True

def clean_build():
    """ビルドファイルをクリーンアップ"""
    import shutil
    
    dirs_to_remove = ["build", "dist", "__pycache__"]
    files_to_remove = ["*.spec"]
    
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"削除: {dir_name}")
    
    # .specファイルを削除
    for spec_file in Path(".").glob("*.spec"):
        spec_file.unlink()
        print(f"削除: {spec_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean_build()
    else:
        build_executable()
