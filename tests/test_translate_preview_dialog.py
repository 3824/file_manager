import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager.filename_translation import TranslationRenameCandidate
from file_manager.translate_preview_dialog import TranslatePreviewDialog


def make_candidate(tmp_path, original_name, translated_name, status="ready", source_language="en"):
    source_path = tmp_path / original_name
    source_path.write_text("x", encoding="utf-8")
    return TranslationRenameCandidate(
        source_path=source_path,
        original_name=original_name,
        translated_name=translated_name,
        source_language=source_language,
        status=status,
    )


def test_preview_dialog_shows_candidates(qtbot, tmp_path):
    candidates = [
        make_candidate(tmp_path, "hello.txt", "こんにちは.txt"),
        make_candidate(tmp_path, "日本語.txt", "日本語.txt", status="skipped_japanese", source_language="ja"),
    ]
    dialog = TranslatePreviewDialog.from_candidates(None, candidates)
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 1).text() == "hello.txt"
    assert dialog.table.item(0, 2).text() == "こんにちは.txt"


def test_preview_dialog_returns_checked_ready_candidates(qtbot, tmp_path):
    candidates = [
        make_candidate(tmp_path, "hello.txt", "こんにちは.txt"),
        make_candidate(tmp_path, "world.txt", "世界.txt"),
    ]
    dialog = TranslatePreviewDialog.from_candidates(None, candidates)
    qtbot.addWidget(dialog)

    dialog.table.item(1, 0).setCheckState(Qt.Unchecked)
    selected = dialog.get_selected_candidates()

    assert [candidate.original_name for candidate in selected] == ["hello.txt"]


def test_preview_dialog_edit_updates_selected_name(qtbot, tmp_path):
    dialog = TranslatePreviewDialog.from_candidates(None, [make_candidate(tmp_path, "hello.txt", "こんにちは.txt")])
    qtbot.addWidget(dialog)

    dialog.table.item(0, 2).setText("やあ")
    selected = dialog.get_selected_candidates()

    assert selected[0].translated_name == "やあ.txt"


def test_preview_dialog_marks_duplicate_names_as_conflict(qtbot, tmp_path):
    candidates = [
        make_candidate(tmp_path, "hello.txt", "同じ.txt"),
        make_candidate(tmp_path, "world.txt", "別名.txt"),
    ]
    dialog = TranslatePreviewDialog.from_candidates(None, candidates)
    qtbot.addWidget(dialog)

    dialog.table.item(1, 2).setText("同じ.txt")

    assert "名前衝突" in dialog.table.item(0, 4).text()
    assert "名前衝突" in dialog.table.item(1, 4).text()


def test_preview_dialog_preserves_unchecked_rows_after_edit(qtbot, tmp_path):
    candidates = [
        make_candidate(tmp_path, "hello.txt", "こんにちは.txt"),
        make_candidate(tmp_path, "world.txt", "世界.txt"),
    ]
    dialog = TranslatePreviewDialog.from_candidates(None, candidates)
    qtbot.addWidget(dialog)
    dialog.table.item(1, 0).setCheckState(Qt.Unchecked)

    dialog.table.item(0, 2).setText("挨拶.txt")

    assert dialog.table.item(1, 0).checkState() == Qt.Unchecked


def test_preview_dialog_clears_resolved_conflict(qtbot, tmp_path):
    candidates = [
        make_candidate(tmp_path, "hello.txt", "同名.txt"),
        make_candidate(tmp_path, "world.txt", "同名.txt"),
    ]
    dialog = TranslatePreviewDialog.from_candidates(None, candidates)
    qtbot.addWidget(dialog)

    dialog.table.item(1, 2).setText("別名.txt")

    assert [candidate.status for candidate in dialog.candidates] == ["ready", "ready"]


def test_preview_dialog_rejects_path_separator_in_name(qtbot, tmp_path):
    dialog = TranslatePreviewDialog.from_candidates(
        None,
        [make_candidate(tmp_path, "hello.txt", "こんにちは.txt")],
    )
    qtbot.addWidget(dialog)

    dialog.table.item(0, 2).setText("sub/name.txt")

    assert dialog.candidates[0].status == "error_invalid_name"
