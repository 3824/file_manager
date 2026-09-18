#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller用のビルドスクリプト

使い方:
  python build_exe.py         # EXEをビルド
  python build_exe.py clean   # ビルド成果物を削除
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


APP_NAME = "GUIファイラー"
ENTRY_POINT = "run.py"


def build_executable() -> bool:
    """実行ファイルをビルドする。"""

    # PyInstaller コマンドを構築
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # 単一EXEにまとめる
        "--windowed",          # コンソールウィンドウを非表示
        f"--name={APP_NAME}",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtMultimedia",
        "--collect-submodules=file_manager",
        "--paths=src",
        ENTRY_POINT,
    ]

    # アイコンファイルが存在する場合は追加
    icon_path = Path("assets/icons/app_icon.ico")
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])

    print("=" * 60)
    print("ビルド開始")
    print("コマンド:", " ".join(cmd))
    print("=" * 60)

    try:
        result = subprocess.run(cmd, check=True)
        print("=" * 60)
        print("ビルド完了！")
        print(f"実行ファイル: dist/{APP_NAME}.exe")
        print("=" * 60)
        return True

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ビルドに失敗しました: {e}")
        return False

    except FileNotFoundError:
        print("[ERROR] PyInstallerが見つかりません。以下を実行してください:")
        print("  pip install pyinstaller")
        return False


def clean_build() -> None:
    """ビルド成果物を削除する。"""
    targets = ["build", "dist", "__pycache__"]
    for name in targets:
        path = Path(name)
        if path.exists():
            shutil.rmtree(path)
            print(f"削除: {name}/")

    for spec_file in Path(".").glob("*.spec"):
        spec_file.unlink()
        print(f"削除: {spec_file}")

    print("クリーンアップ完了")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean_build()
    else:
        success = build_executable()
        sys.exit(0 if success else 1)
