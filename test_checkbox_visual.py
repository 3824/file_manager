#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チェックボックスの視覚確認スクリプト"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.file_manager.filename_similarity_dialog import FilenameSimilarityDialog
from src.file_manager.filename_similarity import SimilarFileGroup


def main():
    """チェックボックスを実際に表示"""
    app = QApplication(sys.argv)

    # テスト用のフォルダを作成
    with tempfile.TemporaryDirectory() as tmpdir:
        # テストファイルを作成
        test_files = [
            ("video_01.mp4", 1000),
            ("video_02.mp4", 1010),
            ("video_03.mp4", 1020),
        ]

        for filename, size in test_files:
            file_path = Path(tmpdir) / filename
            file_path.write_bytes(b"0" * size)

        # ダイアログを作成
        dialog = FilenameSimilarityDialog(tmpdir)

        # テストグループを直接作成
        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[str(Path(tmpdir) / f) for f, _ in test_files],
                similarity_score=0.95,
                file_sizes={str(Path(tmpdir) / f): s for f, s in test_files},
            )
        ]

        # ツリーに設定
        dialog._populate_tree(test_groups)
        dialog.select_all_button.setEnabled(True)
        dialog.deselect_all_button.setEnabled(True)

        # チェックボックスの状態を確認
        print("\n=== チェックボックス設定確認 ===")
        top_item = dialog.tree.topLevelItem(0)
        if top_item:
            print(f"グループ: {top_item.text(1)}")
            print(f"子アイテム数: {top_item.childCount()}")

            for i in range(top_item.childCount()):
                child = top_item.child(i)
                print(f"\nファイル {i + 1}:")
                print(f"  名前: {child.text(1)}")
                print(f"  カラム0テキスト: '{child.text(0)}'")
                print(f"  UserCheckableフラグ: {bool(child.flags() & Qt.ItemIsUserCheckable)}")
                print(f"  チェック状態: {child.checkState(0)}")
                print(f"  フラグ一覧: {child.flags()}")

        print("\n=== ダイアログを表示します ===")
        print("各ファイル名の左側にチェックボックスが表示されているか確認してください。")
        print("チェックボックスをクリックして選択できることを確認してください。")

        dialog.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
