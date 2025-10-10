#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チェックボックスの表示を視覚的に確認するスクリプト"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from src.file_manager.filename_similarity_dialog import FilenameSimilarityDialog
from src.file_manager.filename_similarity import SimilarFileGroup


def main():
    """チェックボックスの表示確認"""
    app = QApplication(sys.argv)

    # テスト用のフォルダを作成
    with tempfile.TemporaryDirectory() as tmpdir:
        # テスト用のファイルを作成
        files = [
            ("video_01.mp4", 1000),
            ("video_02.mp4", 1010),
            ("video_03.mp4", 1020),
            ("movie_a.mp4", 2000),
            ("movie_b.mp4", 2100),
        ]
        for filename, size in files:
            file_path = Path(tmpdir) / filename
            file_path.write_bytes(b"0" * size)

        # ダイアログを作成
        dialog = FilenameSimilarityDialog(tmpdir)

        # テスト用のグループを直接設定
        test_groups = [
            SimilarFileGroup(
                representative_name="video_01.mp4",
                files=[
                    str(Path(tmpdir) / "video_01.mp4"),
                    str(Path(tmpdir) / "video_02.mp4"),
                    str(Path(tmpdir) / "video_03.mp4"),
                ],
                similarity_score=0.95,
                file_sizes={
                    str(Path(tmpdir) / "video_01.mp4"): 1000,
                    str(Path(tmpdir) / "video_02.mp4"): 1010,
                    str(Path(tmpdir) / "video_03.mp4"): 1020,
                },
            ),
            SimilarFileGroup(
                representative_name="movie_a.mp4",
                files=[
                    str(Path(tmpdir) / "movie_a.mp4"),
                    str(Path(tmpdir) / "movie_b.mp4"),
                ],
                similarity_score=0.88,
                file_sizes={
                    str(Path(tmpdir) / "movie_a.mp4"): 2000,
                    str(Path(tmpdir) / "movie_b.mp4"): 2100,
                },
            ),
        ]

        # ツリーに結果を設定
        dialog._populate_tree(test_groups)
        dialog.select_all_button.setEnabled(True)
        dialog.deselect_all_button.setEnabled(True)

        # チェックボックスの存在確認
        top_item = dialog.tree.topLevelItem(0)
        if top_item and top_item.childCount() > 0:
            child = top_item.child(0)
            has_checkbox = child.flags() & Qt.ItemIsUserCheckable
            check_state = child.checkState(0)

            info_msg = f"""
チェックボックス確認結果:

1. グループ数: {dialog.tree.topLevelItemCount()}
2. 最初のグループのファイル数: {top_item.childCount()}
3. チェックボックスフラグ: {bool(has_checkbox)}
4. 初期チェック状態: {check_state} (0=Unchecked, 2=Checked)

【確認事項】
✓ 各ファイル名の左側にチェックボックスが表示されているか
✓ チェックボックスをクリックできるか
✓ 「すべて選択」ボタンが動作するか
✓ チェックすると「チェック済み: N ファイル」が更新されるか
✓ 「チェック済みファイルを削除」ボタンが有効になるか
"""
            print(info_msg)
            QMessageBox.information(dialog, "チェックボックス確認", info_msg)

        dialog.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
