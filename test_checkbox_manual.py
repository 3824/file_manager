#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チェックボックス機能の手動テスト"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.file_manager.filename_similarity_dialog import FilenameSimilarityDialog


def main():
    """チェックボックスが表示されるかテスト"""
    app = QApplication(sys.argv)

    # テスト用のフォルダを作成
    with tempfile.TemporaryDirectory() as tmpdir:
        # 類似ファイルを作成
        files = [
            ("video_01.mp4", 1000),
            ("video_02.mp4", 1010),
            ("video_03.mp4", 1020),
        ]
        for filename, size in files:
            file_path = Path(tmpdir) / filename
            file_path.write_bytes(b"0" * size)

        # ダイアログを表示
        dialog = FilenameSimilarityDialog(tmpdir)
        dialog.show()

        print(f"テストフォルダ: {tmpdir}")
        print("ダイアログを表示しました。")
        print("1. 「検索開始」ボタンをクリック")
        print("2. チェックボックスが表示されることを確認")
        print("3. チェックボックスをクリックして選択できることを確認")
        print("4. 「チェック済みファイルを削除」ボタンが有効になることを確認")

        sys.exit(app.exec())


if __name__ == "__main__":
    main()
