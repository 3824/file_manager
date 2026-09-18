#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アプリ内から pytest を実行するためのダイアログ。"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

TEST_SETS = {
    "基本テスト": [
        "tests/test_simple.py",
        "tests/test_models_dataclasses.py",
        "tests/test_filename_similarity.py",
        "tests/test_video_digest.py",
        "tests/test_disk_analysis.py",
        "tests/test_file_search_schema.py",
        "tests/test_file_search_scope.py",
    ],
    "UIテスト": [
        "tests/test_button_actions.py",
        "tests/test_features.py",
        "tests/test_settings.py",
        "tests/test_run.py",
        "tests/test_video_thumbnail_preview.py",
    ],
    "全テスト": [
        "tests/test_simple.py",
        "tests/test_models_dataclasses.py",
        "tests/test_filename_similarity.py",
        "tests/test_video_digest.py",
        "tests/test_disk_analysis.py",
        "tests/test_file_search_schema.py",
        "tests/test_file_search_scope.py",
        "tests/test_button_actions.py",
        "tests/test_features.py",
        "tests/test_settings.py",
        "tests/test_run.py",
        "tests/test_video_thumbnail_preview.py",
    ],
}

SKIP_TESTS = ["test_tree_context_menu_triggers_duplicate"]
SKIP_ENABLED_SETS = {"UIテスト", "全テスト"}


class TestRunnerThread(QThread):
    """バックグラウンドで pytest を実行するスレッド。"""

    output_line = Signal(str)
    finished_signal = Signal(int)

    def __init__(self, test_files: list[str], skip_tests: list[str] | None = None) -> None:
        super().__init__()
        self.test_files = test_files
        self.skip_tests = skip_tests or []
        self._process: subprocess.Popen[str] | None = None

    def stop(self) -> None:
        """実行中プロセスを停止する。"""
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def run(self) -> None:
        cmd = [sys.executable, "-m", "pytest", *self.test_files, "-v"]
        if self.skip_tests:
            skip_expr = " and ".join(f"not {test_name}" for test_name in self.skip_tests)
            cmd += ["-k", skip_expr]

        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if self._process.stdout is not None:
                for line in self._process.stdout:
                    self.output_line.emit(line.rstrip())
            return_code = self._process.wait()
            self.finished_signal.emit(return_code)
        except Exception as error:  # noqa: BLE001
            self.output_line.emit(f"[ERROR] テスト実行エラー: {error}")
            self.finished_signal.emit(1)
        finally:
            self._process = None


class TestRunnerDialog(QDialog):
    """pytest の実行状況を表示するダイアログ。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("テスト実行")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)

        self._thread: TestRunnerThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("テストセット:"))

        self.test_set_combo = QComboBox()
        for name in TEST_SETS:
            self.test_set_combo.addItem(name)
        header_layout.addWidget(self.test_set_combo)
        header_layout.addStretch()

        self.run_button = QPushButton("テスト実行")
        self.run_button.clicked.connect(self._run_tests)
        header_layout.addWidget(self.run_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_tests)
        header_layout.addWidget(self.stop_button)

        layout.addLayout(header_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QFont("Consolas", 9))
        self.output_area.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        layout.addWidget(self.output_area)

        self.status_label = QLabel("テストセットを選択して実行してください。")
        layout.addWidget(self.status_label)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.close)
        close_layout.addWidget(close_button)
        layout.addLayout(close_layout)

    def _run_tests(self) -> None:
        selected = self.test_set_combo.currentText()
        test_files = TEST_SETS[selected]
        skip_tests = SKIP_TESTS if selected in SKIP_ENABLED_SETS else []

        self.output_area.clear()
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.status_label.setText(f"実行中: {selected}")

        self._thread = TestRunnerThread(test_files, skip_tests)
        self._thread.output_line.connect(self._append_output)
        self._thread.finished_signal.connect(self._on_finished)
        self._thread.start()

    def _stop_tests(self) -> None:
        thread = self._thread
        if thread and thread.isRunning():
            thread.stop()
            thread.wait()
            self.status_label.setText("テストを停止しました。")
        self._reset_buttons()

    def _append_output(self, line: str) -> None:
        """出力を色分けしながら末尾に追加する。"""
        if "PASSED" in line or "passed" in line:
            color = "#4ec9b0"
        elif "FAILED" in line or "ERROR" in line or "error" in line:
            color = "#f48771"
        elif "SKIPPED" in line or "WARNING" in line:
            color = "#dcdcaa"
        elif line.startswith("=") or line.startswith("_"):
            color = "#9cdcfe"
        else:
            color = "#d4d4d4"

        self.output_area.setTextColor(QColor(color))
        self.output_area.append(line)
        self.output_area.ensureCursorVisible()

    def _on_finished(self, return_code: int) -> None:
        self._reset_buttons()
        if return_code == 0:
            self.status_label.setText("テスト完了: すべて成功")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText(f"テスト完了: 失敗あり (終了コード: {return_code})")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self._thread = None

    def _reset_buttons(self) -> None:
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

    def closeEvent(self, event) -> None:
        thread = self._thread
        if thread and thread.isRunning():
            thread.stop()
            thread.wait()
        super().closeEvent(event)
