import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager.disk_analyzer import DiskAnalyzer


def test_disk_analyzer_emits_progress(qtbot, tmp_path):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)

    (root / "a.txt").write_bytes(b"a" * 128)
    (nested / "b.txt").write_bytes(b"b" * 256)

    analyzer = DiskAnalyzer()

    progress_values = []
    analyzer.progress_updated.connect(progress_values.append)

    analyzer.analysis_completed.connect(lambda _: None)
    analyzer.error_occurred.connect(lambda message: pytest.fail(f"analysis error: {message}"))

    analyzer.analyze_directory(str(root))

    assert progress_values, "progress should be emitted"
    assert progress_values[0] == 0
    assert progress_values[-1] == 100
    assert any(0 < value < 100 for value in progress_values), "intermediate progress expected"

