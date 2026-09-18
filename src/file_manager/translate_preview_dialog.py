"""翻訳プレビューダイアログ。"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .filename_translation import (
    INVALID_FILENAME_CHARS,
    FilenameTranslationService,
    TranslationRenameCandidate,
    has_invalid_filename_component,
)
from .logger import logger

CHECKBOX_COLUMN = 0


class CheckboxColumnTableWidget(QTableWidget):
    """「適用」列はセル内のどこをクリックしてもチェックを切り替えられるテーブル。

    QTableWidgetItem のデフォルト実装は、実際に描画される小さなチェック
    インジケーターの上を正確にクリックしないと反応しない。列の的が
    小さすぎて「チェックボックスが機能していない」ように見えるため、
    列0のセル内であればどこをクリックしても切り替わるようにする。
    """

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.column() == CHECKBOX_COLUMN:
                item = self.item(index.row(), CHECKBOX_COLUMN)
                if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                    new_state = (
                        Qt.Unchecked
                        if item.checkState() == Qt.Checked
                        else Qt.Checked
                    )
                    item.setCheckState(new_state)
                    event.accept()
                    return
        super().mousePressEvent(event)


STATUS_LABELS = {
    "ready": "適用可",
    "skipped_japanese": "日本語のため対象外",
    "skipped_no_text": "文字なし",
    "skipped_not_file": "ファイル以外",
    "skipped_same_name": "変更なし",
    "error_api": "翻訳失敗",
    "error_conflict": "名前衝突",
    "error_invalid_name": "不正な名前",
}
EDITABLE_STATUSES = {"ready", "error_conflict", "error_invalid_name"}


class TranslationWorker(QObject):
    """バックグラウンドで翻訳APIを呼び出すワーカー。"""

    progress = Signal(int, int)  # current, total
    finished = Signal(list)  # list[TranslationRenameCandidate]
    error = Signal(str)
    done = Signal()

    def __init__(
        self,
        translator: FilenameTranslationService,
        paths: list[Path],
        target_language: str = "ja",
    ) -> None:
        super().__init__()
        self._translator = translator
        self._paths = paths
        self._target_language = target_language
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """翻訳処理を実行する（ワーカースレッドから呼ばれる）。"""
        try:
            candidates = self._translator.translate_paths(
                self._paths,
                target_language=self._target_language,
                progress_callback=self._on_progress,
                cancel_check=lambda: self._cancelled,
            )
            if not self._cancelled:
                self.finished.emit(candidates)
        except Exception as exc:
            if not self._cancelled:
                logger.exception(
                    "ファイル名の日本語翻訳ワーカーで予期しないエラーが発生しました "
                    "(target_language=%s, file_count=%d): %s",
                    self._target_language,
                    len(self._paths),
                    exc,
                )
                self.error.emit(str(exc))
        finally:
            self.done.emit()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)


class TranslatePreviewDialog(QDialog):
    """翻訳結果確認用ダイアログ。"""

    def __init__(
        self,
        parent,
        translator: FilenameTranslationService,
        paths: list[Path],
    ) -> None:
        super().__init__(parent)
        self._updating_table = False
        self.candidates: list[TranslationRenameCandidate] = []
        self._selected_source_paths: set[Path] = set()
        self._worker: TranslationWorker | None = None
        self._thread: QThread | None = None
        self.setWindowTitle("ファイル名翻訳プレビュー")
        self.resize(900, 480)
        self._init_ui()
        self._start_translation(translator, paths)

    @classmethod
    def from_candidates(
        cls,
        parent,
        candidates: list[TranslationRenameCandidate],
    ) -> "TranslatePreviewDialog":
        """テスト用: 翻訳済みの候補を直接渡してダイアログを生成する。"""
        dialog = QDialog.__new__(cls)
        QDialog.__init__(dialog, parent)
        dialog._updating_table = False
        dialog.candidates = list(candidates)
        dialog._selected_source_paths = set()
        dialog._worker = None
        dialog._thread = None
        dialog.setWindowTitle("ファイル名翻訳プレビュー")
        dialog.resize(900, 480)
        dialog._init_ui()
        # プログレスを非表示にしてテーブルをすぐ表示
        dialog.progress_label.setVisible(False)
        dialog.progress_bar.setVisible(False)
        dialog.table.setVisible(True)
        dialog._populate_table()
        dialog._revalidate_ready_candidates()
        dialog.button_box.addButton(QDialogButtonBox.Ok)
        dialog.button_box.accepted.connect(dialog.accept)
        return dialog

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "翻訳候補を確認し、適用する行だけチェックしてください。"
            "翻訳後の名前はダブルクリックで編集できます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # プログレス表示エリア
        self.progress_label = QLabel("翻訳を実行しています...")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)  # 不定プログレス（パルス表示）
        layout.addWidget(self.progress_bar)

        self.table = CheckboxColumnTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["適用", "元の名前", "翻訳後の名前", "言語", "状態"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 260)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setVisible(False)  # 翻訳完了まで非表示
        layout.addWidget(self.table)

        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _start_translation(self, translator: FilenameTranslationService, paths: list[Path]) -> None:
        """バックグラウンドで翻訳処理を開始する。"""
        self._worker = TranslationWorker(translator, paths)
        # キャンセル後も通信が戻るまではスレッドを生存させる必要があるため、
        # ダイアログではなくアプリケーションを所有者にする。
        self._thread = QThread(QApplication.instance())
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_translation_finished)
        self._worker.error.connect(self._on_translation_error)
        self._worker.done.connect(self._worker.deleteLater)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_progress(self, current: int, total: int) -> None:
        """翻訳進捗を更新する。"""
        if self.progress_bar.maximum() != total:
            self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"翻訳を実行しています... ({current}/{total})")

    def _on_translation_finished(self, candidates: list[TranslationRenameCandidate]) -> None:
        """翻訳完了時にテーブルを表示する。"""
        self.candidates = list(candidates)

        # プログレスを非表示にしてテーブルを表示
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.table.setVisible(True)

        self._populate_table()
        self._revalidate_ready_candidates()

        # OKボタンを追加
        self.button_box.addButton(QDialogButtonBox.Ok)
        self.button_box.accepted.connect(self.accept)

    def _on_translation_error(self, error_message: str) -> None:
        """翻訳エラー時の表示。"""
        self.progress_bar.setVisible(False)
        self.progress_label.setText(f"翻訳中にエラーが発生しました: {error_message}")
        self.progress_label.setStyleSheet("color: red;")

    def _on_thread_finished(self) -> None:
        """ワーカースレッドの自然終了後に参照を解放する。"""
        self._worker = None
        self._thread = None

    def _cleanup_worker(self) -> None:
        """処理をキャンセルする。通信中のスレッドは自然終了を待つ。"""
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.requestInterruption()

    def closeEvent(self, event) -> None:
        """ダイアログを閉じる際にワーカーを停止する。"""
        self._cleanup_worker()
        super().closeEvent(event)

    def reject(self) -> None:
        """キャンセル時にワーカーを停止する。"""
        self._cleanup_worker()
        super().reject()

    def _populate_table(self) -> None:
        self._selected_source_paths = {
            candidate.source_path for candidate in self.candidates if candidate.is_ready
        }
        self._updating_table = True
        try:
            self.table.setRowCount(len(self.candidates))
            for row, candidate in enumerate(self.candidates):
                self._set_row(row, candidate)
        finally:
            self._updating_table = False
        self._update_summary()

    def _set_row(self, row: int, candidate: TranslationRenameCandidate) -> None:
        apply_item = QTableWidgetItem()
        if candidate.is_ready:
            apply_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            apply_item.setCheckState(
                Qt.Checked
                if candidate.source_path in self._selected_source_paths
                else Qt.Unchecked
            )
        else:
            apply_item.setFlags(Qt.ItemIsEnabled)
            apply_item.setCheckState(Qt.Unchecked)
        self.table.setItem(row, 0, apply_item)

        original_item = QTableWidgetItem(candidate.original_name)
        original_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(row, 1, original_item)

        translated_item = QTableWidgetItem(candidate.translated_name)
        translated_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if candidate.status in EDITABLE_STATUSES:
            translated_flags |= Qt.ItemIsEditable
        translated_item.setFlags(translated_flags)
        self.table.setItem(row, 2, translated_item)

        language_item = QTableWidgetItem(candidate.source_language or "-")
        language_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(row, 3, language_item)

        status_text = STATUS_LABELS.get(candidate.status, candidate.status)
        if candidate.message:
            status_text = f"{status_text}: {candidate.message}"
        status_item = QTableWidgetItem(status_text)
        status_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if candidate.status.startswith("error"):
            status_item.setForeground(Qt.red)
        self.table.setItem(row, 4, status_item)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table:
            return

        row = item.row()
        candidate = self.candidates[row]
        if item.column() == 2 and candidate.status in EDITABLE_STATUSES:
            edited_name = item.text().strip()
            if not edited_name:
                edited_name = candidate.original_name
            if Path(edited_name).suffix != candidate.source_path.suffix:
                edited_name = f"{edited_name}{candidate.source_path.suffix}"
            self.candidates[row] = replace(candidate, translated_name=edited_name, status="ready", message="")
            self._revalidate_ready_candidates()
        elif item.column() == 0:
            if item.checkState() == Qt.Checked:
                self._selected_source_paths.add(candidate.source_path)
            else:
                self._selected_source_paths.discard(candidate.source_path)
            self._update_summary()

    def _revalidate_ready_candidates(self) -> None:
        ready_indices = [
            index for index, candidate in enumerate(self.candidates) if candidate.status in EDITABLE_STATUSES
        ]
        updated_candidates = list(self.candidates)
        duplicate_targets: dict[tuple[Path, str], int] = {}

        for index in ready_indices:
            candidate = replace(updated_candidates[index], status="ready", message="")
            updated_candidates[index] = candidate
            target_name = os.path.normcase(candidate.translated_name)
            duplicate_targets[(candidate.source_path.parent, target_name)] = (
                duplicate_targets.get((candidate.source_path.parent, target_name), 0) + 1
            )

        for index in ready_indices:
            candidate = updated_candidates[index]
            if has_invalid_filename_component(candidate.translated_name):
                updated_candidates[index] = replace(
                    candidate,
                    status="error_invalid_name",
                    message=f"禁止文字 {INVALID_FILENAME_CHARS} は使用できません。",
                )
                continue

            target_key = (
                candidate.source_path.parent,
                os.path.normcase(candidate.translated_name),
            )
            target_path = candidate.source_path.with_name(candidate.translated_name)
            if duplicate_targets.get(target_key, 0) > 1 or (
                target_path.exists() and target_path != candidate.source_path
            ):
                updated_candidates[index] = replace(
                    candidate,
                    status="error_conflict",
                    message="他のファイル名と衝突しています。",
                )

        self.candidates = updated_candidates
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        self._updating_table = True
        try:
            for row, candidate in enumerate(self.candidates):
                self._set_row(row, candidate)
        finally:
            self._updating_table = False
        self._update_summary()

    def _update_summary(self) -> None:
        checked_count = sum(
            1
            for row, candidate in enumerate(self.candidates)
            if candidate.is_ready and self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
        )
        ready_count = sum(1 for candidate in self.candidates if candidate.is_ready)
        self.summary_label.setText(f"適用対象: {checked_count} / {ready_count} 件")

    def get_selected_candidates(self) -> list[TranslationRenameCandidate]:
        """チェックされた適用候補だけ返す。"""
        selected: list[TranslationRenameCandidate] = []
        for row, candidate in enumerate(self.candidates):
            apply_item = self.table.item(row, 0)
            if candidate.is_ready and apply_item and apply_item.checkState() == Qt.Checked:
                translated_name = self.table.item(row, 2).text().strip()
                selected.append(replace(candidate, translated_name=translated_name))
        return selected
