import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_manager.file_search import FileSearchIndex


@pytest.mark.parametrize("query", ["report", "REPORT"])
def test_search_files_scoped_results(tmp_path, query):
    root = tmp_path / "root"
    sub_a = root / "project_a"
    sub_b = root / "project_b"
    sub_a.mkdir(parents=True)
    sub_b.mkdir(parents=True)

    target_in_a = sub_a / "report.txt"
    target_in_b = sub_b / "report.txt"
    target_in_a.write_text("alpha", encoding="utf-8")
    target_in_b.write_text("beta", encoding="utf-8")

    index_path = tmp_path / "index.db"
    search_index = FileSearchIndex(index_db_path=str(index_path))
    search_index.update_index_for_directory(str(root))

    scoped_results = search_index.search_files(
        query,
        search_type="name",
        limit=10,
        scope_path=str(sub_a),
    )

    assert [Path(item["path"]).parent for item in scoped_results] == [sub_a]

    global_results = search_index.search_files(query, search_type="name", limit=10)
    assert len(global_results) == 2


